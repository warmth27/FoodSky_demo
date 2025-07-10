import json
import os
import jieba
import copy
import asyncio
import time
from collections import defaultdict
from rank_bm25 import BM25Okapi
import logging
import concurrent.futures
from functools import partial
from logging.handlers import TimedRotatingFileHandler
import numpy as np
from flask import Flask, jsonify, request

import config
from concurrent.futures import ThreadPoolExecutor
app = Flask(__name__)

from openai import OpenAI
client = OpenAI(
    base_url="http://localhost:8003/v1",
    api_key="EMPYT", # 随便填写，只是为了通过接口参数校验
)

###绑定配置文件
UPLOAD_FOLDER = './uploadfile'  # 请根据需要修改
log_path="./logs"
if not os.path.exists(UPLOAD_FOLDER):
    os.mkdir(UPLOAD_FOLDER)
if not os.path.exists(log_path):
    os.mkdir(log_path)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

app.config.from_object(config)

nutritionDataset_path = "/nfs/data/project/xcx_app_project/nutritionDatabase.json"
recipeDataset_path = "/nfs/data/project/xcx_app_project/recipeDataset.json"
nutri_range_Dataset_path = "/nfs/data/project/xcx_app_project/base_nutri_range.json"

with open(nutritionDataset_path,'r',encoding='utf-8')as f:
    nutritionDataset = json.load(f)
with open(recipeDataset_path,'r',encoding='utf-8')as f:
    recipeDataset = json.load(f)
with open(nutri_range_Dataset_path,'r',encoding='utf-8')as f:
    nutriRangeDataset = json.load(f)
    
#! 设置三餐比例
scale = {
    "早餐": 0.3,
    "午餐": 0.4,
    "晚餐": 0.3
}

gender_map = {
    "男":"male",
    "女":"female"
}


def setup_logger(log_name, log_file):
    logger = logging.getLogger(log_name)
    logger.setLevel(logging.INFO)

    # 日志文件每日轮转
    handler = TimedRotatingFileHandler(
        filename=log_file, when="midnight", interval=1, backupCount=7, encoding="utf-8"
    )
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


#! 将ug单位转换为mg单位
def convert_microgram_fields_to_mg(nutrition_dict, field):
    value = nutrition_dict.get(field)
    if value is None:
        return  # 如果该字段不存在则跳过

    if isinstance(value, (int, float)):
        nutrition_dict[field] = round(value / 1000, 6)
    elif isinstance(value, str):
        value = value.strip()
        if '-' in value:
            try:
                parts = value.split('-')
                converted = [str(round(float(p.strip()) / 1000, 6)) for p in parts]
                nutrition_dict[field] = '-'.join(converted)
            except ValueError:
                pass
        else:
            try:
                nutrition_dict[field] = round(float(value) / 1000, 6)
            except ValueError:
                pass


#! 基于BM25的菜品名称匹配
def match_dish_name_bm25(query, dishes):
    tokenized_corpus = [list(jieba.cut(d)) for d in dishes]
    bm25 = BM25Okapi(tokenized_corpus)
    query_tokens = list(jieba.cut(query))
    scores = bm25.get_scores(query_tokens)
    return dishes[scores.argmax()]


#! 基于用户输入的年龄、性别、，计算用户的营养需求范围
def nutritionDataDict(age,gender,height,weight,activity_level):
    nutriRangeList = list(nutriRangeDataset[gender].keys())
    #data['年龄']    
    if not activity_level:
        activity_level = "a"
    for age_range in nutriRangeList:
        age_range_list = list(map(int, age_range.split("-")))
        if age > min(age_range_list) and age < max(age_range_list):
            nutrition_dict = copy.deepcopy(nutriRangeDataset[gender][age_range])
            print("activity_level",activity_level)
            print(nutrition_dict['能量'])
            nutrition_dict['能量'] = nutrition_dict['能量'][activity_level]
            convert_microgram_fields_to_mg(nutrition_dict, "钼")
            convert_microgram_fields_to_mg(nutrition_dict, "铬")
            convert_microgram_fields_to_mg(nutrition_dict, "硒")
            convert_microgram_fields_to_mg(nutrition_dict, "碘")
            convert_microgram_fields_to_mg(nutrition_dict, "维生素A")
            convert_microgram_fields_to_mg(nutrition_dict, "维生素K")
            convert_microgram_fields_to_mg(nutrition_dict, "维生素B12")
            convert_microgram_fields_to_mg(nutrition_dict, "叶酸")
            convert_microgram_fields_to_mg(nutrition_dict, "生物素")
    if height:
        if isinstance(age,int):
            if gender == "male":
                bmr = 88.362 + (13.397 * weight) + (4.799 * height) - (5.677 * age)
            elif gender == "female":
                bmr = 447.593 + (9.247 * weight) + (3.098 * height) - (4.330 * age)
            else:
                raise ValueError("性别必须为 'male' 或 'female'")

        # 计算每日总能量消耗 (TDEE)
        activity_multipliers = {
            "a": 1.2,
            "b": 1.55,
            "c": 1.9,
            "身体活动水平(轻)": 1.2,
            "身体活动水平(中)": 1.55,
            "身体活动水平(重)": 1.9
        }
        tdee = bmr * activity_multipliers[activity_level]

        # 计算宏量营养素需求
        # 蛋白质: 1.6 克/公斤体重（适用于一般运动人群）
        protein_per_kg = 1.6
        protein_g = protein_per_kg * weight
        protein_calories = protein_g * 4  # 每克蛋白质提供 4 卡路里

        # 脂肪: 占总能量的 25%
        fat_calories = tdee * 0.25
        fat_g = fat_calories / 9  # 每克脂肪提供 9 卡路里

        # 碳水化合物: 剩余能量
        carb_calories = tdee - protein_calories - fat_calories
        carb_g = carb_calories / 4  # 每克碳水化合物提供 4 卡路里

        nutrition_dict["能量"] = round(tdee, 2)
        nutrition_dict["蛋白质"] = round(protein_g, 2)
        nutrition_dict["脂肪"] = round(fat_g, 2)
        nutrition_dict["碳水化合物"] = round(carb_g, 2)
    return nutrition_dict


#! 根据用户信息获取营养推荐范围
def get_nutri_range(data):
    def is_valid(value):

        return value not in [None, '', 'null']

    fields = {
        '性别': is_valid(data.get('性别')),
        '年龄': is_valid(data.get('年龄')),
        '身高': is_valid(data.get('身高')),
        '体重': is_valid(data.get('体重')),
    }
    activity_level = data['activity_level']
    present = {k for k, v in fields.items() if v}
    if present == {'性别', '年龄', '身高', '体重'}:
        gender = gender_map[data['性别']]
        result_nutrition_dict = nutritionDataDict(int(data['年龄']),gender,float(data['身高']),float(data['体重']),activity_level)
    elif present == {'性别', '年龄'}:
        gender = gender_map[data['性别']]
        result_nutrition_dict = nutritionDataDict(int(data['年龄']),gender,None,None,None)
    elif present.issubset({'性别', '年龄'}) or len(present) <= 1:
        return None
    else:
        return f"信息部分存在（{present}），但不满足规则，请补全信息"
    return result_nutrition_dict