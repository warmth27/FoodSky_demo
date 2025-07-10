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
scale = {"早餐": 0.3, "午餐": 0.4, "晚餐": 0.3}

gender_map = {"男":"male","女":"female"}


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


#! 基于用户的年龄、性别等基本信息，计算用户的推荐营养范围
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


#! 提取用户输入的个人信息，获取用户的推荐营养范围
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

#! 计算单个菜品内​​所有食材的总营养成分​，只处理食材
def ingredients_calculate_weight(data):
    if len(data) < 1:
        return None,0
    calories = 0
    fats = 0
    protein = 0
    carbohydrate = 0
    vitamin_B1 = 0
    calcium = 0
    vitamin_B2 = 0
    magnesium = 0
    niacin = 0
    iron = 0
    vitamin_C = 0
    manganese = 0
    insoluble_Dietary_Fiber = 0
    vitamin_E = 0
    zinc = 0
    total_Vitamin_A = 0
    cholesterol = 0
    copper = 0
    carotene = 0
    potassium = 0
    phosphorus = 0
    vitamin_A = 0
    sodium = 0
    selenium = 0
    total_weight = 0
    for each_ingredients in data:
        ingredients_name = each_ingredients[0]
        weight = int(each_ingredients[1])
        total_weight = weight + total_weight
        flat_dict = {list(d.keys())[0]: list(d.values())[0] for d in nutritionDataset[ingredients_name]['content']}
        calories = float(flat_dict.get("能量"))/100 * weight + calories
        fats = float(flat_dict.get("脂肪"))/100*weight + fats
        protein = float(flat_dict.get("蛋白质"))/100*weight + protein
        carbohydrate = float(flat_dict.get("碳水化合物"))/100*weight + carbohydrate
        vitamin_B1 = float(flat_dict.get("硫胺素"))/100*weight + vitamin_B1
        calcium = float(flat_dict.get("钙"))/100*weight + calcium
        vitamin_B2 = float(flat_dict.get("核黄素"))/100*weight + vitamin_B2
        magnesium = float(flat_dict.get("镁"))/100*weight + magnesium
        niacin = float(flat_dict.get("烟酸"))/100*weight + niacin
        iron = float(flat_dict.get("铁"))/100*weight + iron
        vitamin_C = float(flat_dict.get("维生素C"))/100*weight + vitamin_C
        manganese = float(flat_dict.get("锰"))/100*weight + manganese
        insoluble_Dietary_Fiber = float(flat_dict.get("不溶性膳食纤维"))/100*weight + insoluble_Dietary_Fiber
        vitamin_E = float(flat_dict.get("维生素E"))/100*weight + vitamin_E
        zinc = float(flat_dict.get("锌"))/100*weight + zinc
        total_Vitamin_A = float(flat_dict.get("总维生素A"))/100*weight + total_Vitamin_A
        cholesterol = float(flat_dict.get("胆固醇"))/100*weight + cholesterol
        copper = float(flat_dict.get("铜"))/100*weight + copper
        carotene = float(flat_dict.get("胡萝卜素"))/100*weight + carotene
        potassium = float(flat_dict.get("钾"))/100*weight + potassium
        phosphorus = float(flat_dict.get("磷"))/100*weight + phosphorus
        vitamin_A = float(flat_dict.get("视黄醇"))/100*weight + vitamin_A
        sodium = float(flat_dict.get("钠"))/100*weight + sodium
        selenium = float(flat_dict.get("硒"))/100*weight + selenium
    all_nutrition = {
        "能量":calories,
        "脂肪":fats,
        "蛋白质":protein,
        "碳水化合物":carbohydrate,
        "维生素B1":vitamin_B1,
        "钙":calcium,
        "维生素B2":vitamin_B2,
        "镁":magnesium,
        "烟酸":niacin,
        "铁":iron,
        "维生素C":vitamin_C,
        "锰":manganese,
        "不溶性膳食纤维":insoluble_Dietary_Fiber,
        "维生素E":vitamin_E,
        "锌":zinc,
        "总维生素A":total_Vitamin_A,
        "胆固醇":cholesterol,
        "铜":copper,
        "胡萝卜素":carotene,
        "钾":potassium,
        "磷":phosphorus,
        "维生素A":vitamin_A/1000,
        "钠":sodium,
        "硒":selenium / 1000
    }
    return all_nutrition,total_weight
