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
import pulp

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

#! 计算整个餐单的食材，包括处理食材和食谱
def cal_food_nutri(all_food_name):
    total_nutrition_all = {}
    total_food_weight = 0
    total_main_weight = 0
    total_other_weight = 0
    
    # 缓存匹配结果，避免重复匹配
    recipe_cache = {}
    nutrition_cache = {}
    
    for each_food_dict in all_food_name:
        food_name = each_food_dict["食品名称"]
        food_weight = each_food_dict["食品克数"]
        value = each_food_dict.get("食材信息")
        
        total_nutrition = {}
        print("food_name",food_name)
        if isinstance(value, (dict, str)) and value:
            # 处理食材信息
            ingredient_info = each_food_dict['食材信息']
            each_food_list = []
            
            for k, v in ingredient_info.items():
                # 使用缓存避免重复匹配
                if k not in nutrition_cache:
                    matched_food_name = match_dish_name_bm25(k, list(nutritionDataset.keys()))
                    nutrition_cache[k] = matched_food_name
                else:
                    matched_food_name = nutrition_cache[k]
                
                print("matched_food_name", matched_food_name)
                each_food_list.append([matched_food_name, float(v)])
            
            total_nutrition, all_weight = ingredients_calculate_weight(each_food_list)
            
        else:
            # 处理菜品信息
            total_food_weight += int(food_weight)
            
            # 使用缓存避免重复匹配和计算
            if food_name not in recipe_cache:
                matched_food_name = match_dish_name_bm25(food_name, list(recipeDataset.keys()))
                print("matched_food_name", matched_food_name)
                recipe_dict = recipeDataset[matched_food_name]
                
                # 计算食材营养
                main_ingred = recipe_dict['主食材']
                main_ingred_all_nutrition, main_weight = ingredients_calculate_weight(main_ingred)
                other_ingred = recipe_dict['辅料']
                other_ingred_all_nutrition, other_weight = ingredients_calculate_weight(other_ingred)
                
                # 合并营养信息
                if main_ingred_all_nutrition and other_ingred_all_nutrition:
                    combined_nutrition = {}
                    all_keys = set(main_ingred_all_nutrition.keys()) | set(other_ingred_all_nutrition.keys())
                    for key in all_keys:
                        main_value = float(main_ingred_all_nutrition.get(key, 0))
                        other_value = float(other_ingred_all_nutrition.get(key, 0))
                        combined_nutrition[key] = main_value + other_value
                elif main_ingred_all_nutrition:
                    combined_nutrition = main_ingred_all_nutrition
                elif other_ingred_all_nutrition:
                    combined_nutrition = other_ingred_all_nutrition
                else:
                    combined_nutrition = {}
                
                # 缓存结果
                recipe_cache[food_name] = {
                    'nutrition': combined_nutrition,
                    'main_weight': main_weight,
                    'other_weight': other_weight
                }
            else:
                # 使用缓存的结果
                cached_result = recipe_cache[food_name]
                combined_nutrition = cached_result['nutrition']
                main_weight = cached_result['main_weight']
                other_weight = cached_result['other_weight']
            
            total_nutrition = combined_nutrition
            total_main_weight += int(main_weight)
            total_other_weight += int(other_weight)
        
        # 累积营养信息 - 只遍历一次
        if total_nutrition:
            for key, value in total_nutrition.items():
                total_nutrition_all[key] = total_nutrition_all.get(key, 0) + float(value)
    
    # 最终计算 - 过滤和计算一次完成
    if total_main_weight + total_other_weight > 0:
        total_nutrition_all = {
            k: round(float(v) / (total_main_weight + total_other_weight) * total_food_weight, 4) 
            for k, v in total_nutrition_all.items() if float(v) > 0
        }
    
    return total_nutrition_all


# 线性规划实现菜品选择
class DishOptimizer:
    def __init__(self):
        self.logger = setup_logger("optimizer", "logs/optimizer.log")
    
    # 计算用户单餐营养需求（推荐营养范围）
    def calculate_meal_needs(self, user_info, meal_type):
        daily_needs = get_nutri_range(user_info)   # 全日营养需求
        meal_ratio = scale.get(meal_type, 0)  # 获取餐比例，默认0
        
        meal_needs = {}
        for nutrient, value in daily_needs.items():
            if isinstance(value, (int, float)):
                meal_needs[nutrient] = (value * meal_ratio * 0.9, value * meal_ratio * 1.1)  # 缩放0.9-1.1，避免无解
            elif isinstance(value, str) and '-' in value:
                low, high = map(float, value.split('-'))
                meal_needs[nutrient] = (low * meal_ratio * 0.9, high * meal_ratio * 1.1)
            else:
                meal_needs[nutrient] = (0, float('inf'))

        return meal_needs
    # 计算单道菜品的营养范围
    def calculate_dish_nutrition(self, dish):
        dish_data =  [{"食品名称": dish["name"], "食品克数": dish.get("weight", 100)}]
        return cal_food_nutri(dish_data)
    
    #? 使用线性规划优化菜品权重
    def optimize_dish_weights(self, user_needs, dishes):
        """
        使用线性规划优化菜品权重
        :param user_needs: 单餐营养需求字典 {营养名: (min, max)}
        :param dishes: 菜品列表 [{"name": "菜品名", "weight": 重量(g)}]
        :return: 权重列表, 求解状态
        """
        # 创建线性规划问题
        prob = pulp.LpProblem("DishWeightOptimization", pulp.LpMinimize)
        # 关键营养素列表
        key_nutrients = ["能量", "蛋白质", "脂肪", "碳水化合物"]
        # 创建决策变量-每道菜的权重
        weights = [pulp.LpVariable(f"w_{i}", lowBound=0, upBound=1) for i in range(len(dishes))]
        
        # 计算菜品质量评分（此处设置为1）
        dish_scores = [1.0] * len(dishes)
        
        # 设置目标函数：最大化菜品权重与质量评分的点积
        prob += pulp.lpDot(weights, dish_scores), "Total_Quality_Score"
        
        # 计算每道菜的营养范围
        dish_nutritions = []
        for dish in dishes:
            nutrition = self.calculate_dish_nutrition(dish)
            dish_nutritions.append(nutrition)
            
        # 添加营养约束
        for nutrient in key_nutrients:
            # 获取用户需求营养范围
            min_val, max_val = user_needs.get(nutrient, (0, float('inf')))
            if max_val == float('inf'):
                continue
            
            # 计算加权总和
            nutrient_values = [dish.get(nutrient, 0) for dish in dish_nutritions]
            weighted_sum = pulp.lpDot(weights, nutrient_values)
            
            # 添加约束：加权总和在用户需求范围内
            if min_val > 0:
                prob += weighted_sum >= min_val, f"{nutrient}_min"
            if max_val < float('inf'):
                prob += weighted_sum <= max_val, f"{nutrient}_max"
        # 添加权重总和约束（至少选择70%菜品）
        prob += pulp.lpSum(weights) >= 0.7, "Min_70_Percent"
        
        
    
    
    
