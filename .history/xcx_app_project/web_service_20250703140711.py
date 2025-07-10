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

scale = {
    "早餐":0.3,
    "午餐":0.4,
    "晚餐":0.3
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


def match_dish_name_bm25(query, dishes):
    tokenized_corpus = [list(jieba.cut(d)) for d in dishes]
    bm25 = BM25Okapi(tokenized_corpus)
    query_tokens = list(jieba.cut(query))
    scores = bm25.get_scores(query_tokens)
    return dishes[scores.argmax()]

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


def ingredients_calculate_weight(data):
    if len(data) < 1:
        return None,0
    calories = 0
    fats = 0
    protien = 0
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
        protien = float(flat_dict.get("蛋白质"))/100*weight + protien
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
        "蛋白质":protien,
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


gender_map = {
    "男":"male",
    "女":"female"
}

def compare_nutrients(current: dict, recommended: dict):
    def parse_range(value):
        """解析推荐值为均值（处理单值和区间）"""
        if isinstance(value, (int, float)):
            return float(value)
        elif isinstance(value, str):
            if '-' in value:
                low, high = map(float, value.split('-'))
                return (low + high) / 2
            else:
                return float(value)
        else:
            raise ValueError(f"Unsupported type: {value}")
    
    result = {}
    keys_to_compare = ['能量', '蛋白质', '碳水化合物', '脂肪']
    
    for key in keys_to_compare:
        current_val = float(current.get(key, 0))
        if key not in recommended:
            result[key] = '无推荐值'
            continue
        
        target_val = parse_range(recommended[key])
        lower = target_val * 0.98
        upper = target_val * 1.02
        
        if current_val < lower:
            result[key] = '不足'
        elif current_val > upper:
            result[key] = '超量'
        else:
            result[key] = '满足'
    common_keys = current.keys() & recommended.keys()
    common_current = {k: current[k] for k in common_keys}
    common_recommended = {k: recommended[k] for k in common_keys}

    return result, common_current, common_recommended



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
'''
def cal_food_nutri(all_food_name):
    total_nutrition_all = {}
    total_food_weight = 0
    total_main_weight = 0
    total_other_weight = 0
    for each_food_dict in all_food_name:
        food_name = each_food_dict["食品名称"]
        food_weight = each_food_dict["食品克数"]
        value = each_food_dict.get("食材信息")
        if isinstance(value, (dict, str)) and value:
            ingredient_info = each_food_dict['食材信息']
            each_food_list = []
            for k,v in ingredient_info.items():
                matched_food_name = match_dish_name_bm25(k,list(nutritionDataset.keys()))
                print("matched_food_name",matched_food_name)
                each_food_list.append([matched_food_name,float(v)])
            total_nutrition,all_weight = ingredients_calculate_weight(each_food_list)
            if total_nutrition:
                for key, value in total_nutrition.items():
                    total_nutrition_all[key] = total_nutrition_all.get(key, 0) + float(value) 
        else:
            total_food_weight = total_food_weight + int(food_weight)
            matched_food_name = match_dish_name_bm25(food_name,list(recipeDataset.keys()))
            print("matched_food_name",matched_food_name)
            recipe_dict = recipeDataset[matched_food_name]
            #计算食材
            main_ingred = recipe_dict['主食材']
            main_ingred_all_nutrition,main_weight = ingredients_calculate_weight(main_ingred)
            other_ingred = recipe_dict['辅料']
            other_ingred_all_nutrition,other_weight = ingredients_calculate_weight(other_ingred)
            #然后食材用于融合
            total_main_weight = total_main_weight + int(main_weight)
            total_other_weight = total_other_weight + int(other_weight)
            if main_ingred_all_nutrition and other_ingred_all_nutrition:
                total_nutrition = {}
                all_keys = set(main_ingred_all_nutrition.keys()) | set(other_ingred_all_nutrition.keys())
                for key in all_keys:
                    main_value = float(main_ingred_all_nutrition.get(key, 0))
                    other_value = float(other_ingred_all_nutrition.get(key, 0))
                    total_nutrition[key] = main_value + other_value
            elif main_ingred_all_nutrition:
                total_nutrition = main_ingred_all_nutrition
            elif other_ingred_all_nutrition:
                total_nutrition = other_ingred_all_nutrition

        for key, value in total_nutrition.items():
            total_nutrition_all[key] = total_nutrition_all.get(key, 0) + float(value)
    total_nutrition_all = {k: round(float(v) / (total_main_weight + total_other_weight) * total_food_weight, 4) for k, v in total_nutrition_all.items() if float(v) > 0}
    return total_nutrition_all
'''
def recalculate_recommend_nutrition_range(data,scale):
    result = {}
    for key,value in data.items():
        if isinstance(value,str):
            if '-' in value:
                low, high = value.split('-')
                try:
                    low = float(low) * scale
                    high = float(high) * scale
                    result[key] = f"{low:.2f}-{high:.2f}"
                except ValueError:
                    result[key] = value  # 保留原值，无法转为float
            else:
                try:
                    num = float(value) * scale
                    result[key] = f"{num:.2f}"
                except ValueError:
                    result[key] = value  # 同样保留s
        else:
            try:
                num = float(value) * scale
                result[key] = f"{num:.2f}"
            except ValueError:
                result[key] = value  # 同样保留s
    return result

def recalculate_personal_nutrition_range(data,scale):
    result = {}
    for key,value in data.items():
        if '-' in value:
            low, high = value.split('-')
            try:
                low = float(low) * scale
                high = float(high) * scale
                result[key] = f"{low:.2f}-{high:.2f}"
            except ValueError:
                result[key] = value  # 保留原值，无法转为float
        else:
            try:
                num = float(value) * scale
                result[key] = f"{num:.2f}"
            except ValueError:
                result[key] = value  # 同样保留s
    return result

def parse_diet_data(data):
    # 提取用户基本信息
    gender = data['info']['性别']
    age = data['info']['年龄']
    height = data['info']['身高']
    weight = data['info']['体重']
    activity = "未提供" if data['info']['activity_level'] is None else data['info']['activity_level']
    
    # 提取餐别信息
    meal_type = data['data']['餐别']
    # 处理菜品信息
    dishes = []
    for food in data['data']['菜品名称']:
        # 基础菜品信息
        dish_info = f"{food['食品名称']}{food['食品克数']}克"
        
        # 添加食材详细信息（如果有）
        if food['食材信息']:
            ingredients = [f"{ing}{weight}克" for ing, weight in food['食材信息'].items()]
            dish_info += f"（含{''.join(ingredients)}）"
        
        dishes.append(dish_info)
    
    # 组合所有菜品描述
    dishes_str = '和'.join(dishes)
    return f"{data['flag']}天内容，一位{age}岁{gender}性（身高{height}cm，体重{weight}kg，活动水平{activity}，{meal_type}食用了{dishes_str}。"

async def ask(illness,info_data,recommend_nutrition_range,total_nutrition_all_recipe):

    #'''
    #url = "http://192.168.99.55:8003/generate"
    #data = {
    #    "prompt": question
    #}
    print("info_data",info_data)
    print("recommend_nutrition_range",recommend_nutrition_range)
    print("total_nutrition_all_recipe",total_nutrition_all_recipe)
    # 执行curl命令
    #result = requests.post(url, json=data)
    #print("output_2",result.json()["choices"][0]["text"])
    #return result.json()["choices"][0]["text"]
    #'''
    completion = client.chat.completions.create(
        model="FoodSky-7B-Qwen",
        messages=[
            {"role": "system", "content": '你是FoodSky，由中科深健研发的食品大模型'},
            {"role": "user", "content": f"""
                            请根据以下信息，结合个人情况、推荐摄入和当前摄入，生成一句约20字的健康膳食建议：

                            个人信息：
                            {info_data}

                            患病情况：
                            {illness}

                            这个人的推荐摄入量：
                            {recommend_nutrition_range}

                            这个人的当前摄入量：
                            {total_nutrition_all_recipe}

                            请结合推荐与实际摄入量，针对该用户饮食状况，用80字以内给出合理的健康膳食建议。
             """}
        ]
    )
    return completion.choices[0].message.content

def dict_to_text(nutrient_dict):
    parts = []
    for nutrient, value in nutrient_dict.items():
        parts.append(f"{nutrient}为{value}")
    sentence = "包括：" + "，".join(parts) + "。"
    return sentence

app_log = setup_logger("logger", "logs/app_log.log")
@app.post('/getNutrition')
async def getNutrition():  
    json_data = request.get_json() 
    flag = int(json_data.get("flag"))
    info = json_data.get("info")
    data = json_data.get("data")
    output = ""
    if flag == 0:
        cal_scale = scale[data['餐别']]
        food_name = data['菜品名称']
        total_nutrition_all_recipe = cal_food_nutri(food_name)
        recommend_nutrition_range = get_nutri_range(info)
        recommend_nutrition_range = recalculate_recommend_nutrition_range(recommend_nutrition_range,cal_scale)
        total_nutrition_all_recipe = recalculate_recommend_nutrition_range(total_nutrition_all_recipe,cal_scale)
        info_data = parse_diet_data(json_data)
        result,total_nutrition_all_recipe,recommend_nutrition_range = compare_nutrients(total_nutrition_all_recipe,recommend_nutrition_range)
        result_dict = {
            "success":True,
            "本次营养范围":total_nutrition_all_recipe,
            "推荐营养范围":recommend_nutrition_range,
            "营养健康建议":None,
            "message":"访问成功"
        }
        result_dict.update(result)
    elif flag == 1:
        food_name = data['菜品名称']
        total_nutrition_all_recipe = cal_food_nutri(food_name)
        recommend_nutrition_range = get_nutri_range(info)
        info_data = parse_diet_data(json_data)
        illness = "无"
        if info["疾病情况"]:
            illness = info["疾病情况"]
        result,total_nutrition_all_recipe,recommend_nutrition_range = compare_nutrients(total_nutrition_all_recipe,recommend_nutrition_range)
        recommend_nutrition = dict_to_text(recommend_nutrition_range)
        total_nutrition_all_recipe_personal = dict_to_text(total_nutrition_all_recipe)
        #output = await ask(illness,info_data,recommend_nutrition,total_nutrition_all_recipe_personal)
        result_dict = {
            "success":True,
            "本次营养范围":total_nutrition_all_recipe,
            "推荐营养范围":recommend_nutrition_range,
            "营养健康建议":output,
            "message":"访问成功"
        }
        result_dict.update(result)
    elif flag == 7:
        t1 = time.time()
        food_name = data['菜品名称']
        total_nutrition_all_recipe = cal_food_nutri(food_name)
        t2 = time.time()
        recommend_nutrition_range = get_nutri_range(info)
        t3 = time.time()
        print(t2-t1)
        recommend_nutrition_range = recalculate_recommend_nutrition_range(recommend_nutrition_range,7)
        info_data = parse_diet_data(json_data)
        recommend_nutrition = dict_to_text(recommend_nutrition_range)
        total_nutrition_all_recipe_personal = dict_to_text(total_nutrition_all_recipe)
        result,total_nutrition_all_recipe,recommend_nutrition_range = compare_nutrients(total_nutrition_all_recipe,recommend_nutrition_range)
        print(result)
        illness = "无"
        if info["疾病情况"]:
            illness = info["疾病情况"]
        t4 = time.time()
        #output = await ask(illness,info_data,recommend_nutrition,total_nutrition_all_recipe_personal)
        result_dict = {
            "success":True,
            "本次营养范围":total_nutrition_all_recipe,
            "推荐营养范围":recommend_nutrition_range,
            "营养健康建议":output,
            "message":"访问成功"
        }
        result_dict.update(result)
    elif flag == 30:
        food_name = data['菜品名称']
        total_nutrition_all_recipe = cal_food_nutri(food_name)
        recommend_nutrition_range = get_nutri_range(info)
        recommend_nutrition_range = recalculate_recommend_nutrition_range(recommend_nutrition_range,30)
        info_data = parse_diet_data(json_data)
        recommend_nutrition = dict_to_text(recommend_nutrition_range)
        total_nutrition_all_recipe_personal = dict_to_text(total_nutrition_all_recipe)
        result,total_nutrition_all_recipe,recommend_nutrition_range = compare_nutrients(total_nutrition_all_recipe,recommend_nutrition_range)
        illness = "无"
        if info["疾病情况"]:
            illness = info["疾病情况"]
        #output = await ask(illness,info_data,recommend_nutrition,total_nutrition_all_recipe_personal)
        result_dict = {
            "success":True,
            "本次营养范围":total_nutrition_all_recipe,
            "推荐营养范围":recommend_nutrition_range,
            "营养健康建议":output,
            "message":"访问成功"
        }
        result_dict.update(result)
    else:
        #get 访问方式返回
        result_dict = {
                "success":False,
                "本次营养范围":None,
                "推荐营养范围":None,
                "营养健康建议":None,
                "message":f"访问失败，flag应为<0,1,7,30>,但是接收到的flag为<{flag}>"
                }
    print(result_dict)
    app_log.info(f"[Output response] {result_dict}")
    return jsonify(result_dict)#jsonify



#def run_server(port):
    #app.run(host='192.168.2.43', port=port, debug=True,threaded=True)
if __name__ == "__main__":
    app.run(host='192.168.99.55', port=5000, debug=True,threaded=True)
 