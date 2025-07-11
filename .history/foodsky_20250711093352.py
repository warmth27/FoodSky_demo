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
    # 初始化营养字典
    nutrition_dict = {}
    
    # 获取基础营养范围
    nutriRangeList = list(nutriRangeDataset[gender].keys())
    for age_range in nutriRangeList:
        age_range_list = list(map(int, age_range.split("-")))
        if min(age_range_list) <= age <= max(age_range_list):
            nutrition_dict = copy.deepcopy(nutriRangeDataset[gender][age_range])
            break
    
    # 处理活动水平
    if not activity_level:
        activity_level = "a"  # 默认轻等活动水平
    
    # print("activity_level",activity_level)
    # print(nutrition_dict['能量'])
    nutrition_dict['能量'] = nutrition_dict['能量'][activity_level]
    
    # 如果有身高体重，计算个性化需求
    if height and weight:
        if isinstance(age, int):
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
            tdee = bmr * activity_multipliers.get(activity_level, 1.2)

            # 计算宏量营养素需求
            protein_per_kg = 1.6
            protein_g = protein_per_kg * weight
            protein_calories = protein_g * 4

            fat_calories = tdee * 0.25
            fat_g = fat_calories / 9

            carb_calories = tdee - protein_calories - fat_calories
            carb_g = carb_calories / 4

            # 更新宏量营养素
            nutrition_dict.update({
                "能量": round(tdee, 2),
                "蛋白质": round(protein_g, 2),
                "脂肪": round(fat_g, 2),
                "碳水化合物": round(carb_g, 2)
            })
    
    # 单位转换
    microgram_fields = ["钼", "铬", "硒", "碘", "维生素A", "维生素K", "维生素B12", "叶酸", "生物素"]
    for field in microgram_fields:
        convert_microgram_fields_to_mg(nutrition_dict, field)
    
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
        result_nutrition_dict = nutritionDataDict(int(data['年龄']),gender,None,None,activity_level)
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

# 缓存匹配结果，避免重复匹配
recipe_cache = {}
nutrition_cache = {}


#! 计算整个餐单的食材，包括处理食材和食谱
def cal_food_nutri(all_food_name):
    global recipe_cache, nutrition_cache
        
    total_nutrition_all = {}
    total_food_weight = 0
    total_main_weight = 0
    total_other_weight = 0
    
    for each_food_dict in all_food_name:
        food_name = each_food_dict["食品名称"]
        food_weight = each_food_dict["食品克数"]
        value = each_food_dict.get("食材信息")
        
        # total_nutrition = {}
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
            # 累加营养
            for key, value in total_nutrition.items():
                total_nutrition_all[key] = total_nutrition_all.get(key, 0) + float(value)
            
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
                    
                recipe_total_weight = main_weight + other_weight
                
                # 缓存结果
                recipe_cache[food_name] = {
                    'nutrition': combined_nutrition,
                    'total_weight': recipe_total_weight,
                }
            else:
                # 使用缓存的结果
                cached_result = recipe_cache[food_name]
                combined_nutrition = cached_result['nutrition']
                recipe_total_weight = cached_result['total_weight']
                    
            # 计算缩放比例
            if recipe_total_weight > 0:
                scale_factor = float(food_weight) / recipe_total_weight
                scaled_nutrition = {k: v * scale_factor for k, v in combined_nutrition.items()}
            else:
                scaled_nutrition = {}
                
            # 累加缩放后的营养
            for key, value in scaled_nutrition.items():
                total_nutrition_all[key] = total_nutrition_all.get(key, 0) + float(value)
    
    return total_nutrition_all

#! 验证菜品数据格式
def validate_dish(dish):
    """验证菜品数据格式"""
    if not isinstance(dish, dict):
        return False
    if "食品名称" not in dish:
        return False
    if "食品克数" not in dish:
        return False
    return True

#! 生成所有菜品的推荐理由 Foodsky
def generate_all_dishes_reasons(dishes_info, meal_needs, weights, user_info, meal_type):
    """
    批量生成所有菜品的推荐理由
    :param dishes_info: 菜品信息列表 [{
        "name": "菜品名",
        "nutrition": {营养数据},
        "weight": 推荐权重
    }]
    :param meal_needs: 单餐营养需求
    :param weights: 推荐权重列表
    :return: 推荐理由列表
    """
    print({json.dumps(user_info, indent=2, ensure_ascii=False)})
    print({format_nutrition_table(meal_needs, is_range=True)})
    print({format_dishes_table(dishes_info)})
    # 准备提示词
    prompt = f"""
你是一位专业的营养师，正在为用户设计一份完整的{meal_type}餐单。以下是餐单中的14道菜品信息，请为每道菜品生成专业的推荐理由：

## 用户基本信息:{json.dumps(user_info, indent=2, ensure_ascii=False)}

### 营养需求:{format_nutrition_table(meal_needs, True)}

## 菜品信息列表:{format_dishes_table(dishes_info)}

## 任务要求
1. 为每道菜品生成独立的推荐理由（30字）
2. 分析菜品的主要营养特点
3. 结合推荐权重解释原因（权重高说明营养均衡，权重低说明营养不均衡）
4. 给出具体食用建议
5. 语言简洁专业，适合普通用户理解

## 输出格式使用JSON格式输出
"""
    
    try:
        # 调用大模型
        response = client.chat.completions.create(
            model="FoodSky-7B-Qwen",
            messages=[
                {"role": "system", "content": "你是一位专业的营养师，为多道菜品生成简洁的推荐理由。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=800,
            temperature=0.7,
            response_format={"type": "json_object"}  # 要求返回JSON
        )
        
        # 解析JSON结果
        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        app_log.error(f"大模型批量生成推荐理由失败: {str(e)}")
    
        return generate_simple_reasons(dishes_info, weights)

#! todo 简单生成推荐理由
def generate_simple_reasons(dishes_info, weights):
    reasons = {}
    return reasons
    


# 精简后
def format_dishes_table(dishes_info):
    return "\n".join([
        f"菜品: {dish['name']}, 权重: {dish['weight']:.2f}, 营养: [{format_nutrition_table(dish['nutrition'])}]"
        for dish in dishes_info
    ])

def format_nutrition_table(nutrition_data, is_range=False):
    # 只显示核心营养素
    key_nutrients = ["能量", "蛋白质", "脂肪", "碳水化合物"]
    return ";".join([
        f"{nut}:{nutrition_data.get(nut, 0):.1f}" 
        for nut in key_nutrients
    ])

# 线性规划实现菜品选择
class DishOptimizer:
    def __init__(self):
        self.logger = setup_logger("optimizer", "logs/optimizer.log")
    
    # 计算用户单餐营养需求（推荐营养范围）
    def calculate_meal_needs(self, user_info, meal_type):
        daily_needs = get_nutri_range(user_info)   # 全日营养需求
        meal_ratio = scale.get(meal_type, 0.4)  # 获取餐比例，默认0.4
        
        meal_needs = {}
        for nutrient, value in daily_needs.items():
            if isinstance(value, (int, float)):
                meal_needs[nutrient] = (value * meal_ratio * 0.9, value * meal_ratio * 1.1)  # 缩放0.9-1.1，避免无解
            elif isinstance(value, str) and '-' in value:
                low, high = map(float, value.split('-'))
                meal_needs[nutrient] = (low * meal_ratio, high * meal_ratio)
            else:
                meal_needs[nutrient] = (0, float('inf'))

        return meal_needs
    # 计算单道菜品的营养范围
    def calculate_dish_nutrition(self, dish):
        """计算单道菜品营养值"""
        # 直接调用 cal_food_nutri 函数
        dish_data = [{
            "食品名称": dish["name"], 
            "食品克数": dish.get("weight", 100)
        }]
        return cal_food_nutri(dish_data)
    
    #! 使用线性规划优化菜品权重
    def optimize_dish_weights(self, user_needs, dishes):
        """
        使用线性规划优化菜品权重
        :param user_needs: 单餐营养需求字典 {营养名: (min, max)}
        :param dishes: 菜品列表 [{"name": "菜品名", "weight": 重量(g)}]
        :return: 权重列表, 求解状态
        """
        # 创建线性规划问题
        prob = pulp.LpProblem("DishWeightOptimization", pulp.LpMaximize)
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
                
        # 添加微量营养素约束（宽松约束）
        micronutrients = ["钙", "铁", "维生素C", "维生素A"]
        for nutrient in micronutrients:
            min_val, max_val = user_needs.get(nutrient, (0, float('inf')))
            if max_val < float('inf'):
                nutrient_values = [dish.get(nutrient, 0) for dish in dish_nutritions]
                weighted_sum = pulp.lpDot(weights, nutrient_values)
                prob += weighted_sum <= max_val * 1.5, f"{nutrient}_max"  # 宽松上限
        
        # 添加弹性约束（避免无解）
        for nutrient in key_nutrients:
            min_val, max_val = user_needs.get(nutrient, (0, float('inf')))
            if min_val > 0 and max_val < float('inf'):
                nutrient_values = [dish.get(nutrient, 0) for dish in dish_nutritions]
                weighted_sum = pulp.lpDot(weights, nutrient_values)
                # 允许10%的偏差
                prob += weighted_sum >= min_val * 0.9, f"{nutrient}_min_relaxed"
                prob += weighted_sum <= max_val * 1.1, f"{nutrient}_max_relaxed"
        
        # 添加权重总和约束（至少选择70%菜品）
        prob += pulp.lpSum(weights) >= 0.7, "Min_70_Percent"
        # 添加每道菜品的最小重量约束（至少选择5%，避免权重为0，可选）
        for i, w in enumerate(weights):
            prob += w >= 0.05, f"Min_Weight_{i}"
        
        # 求解问题
        solver = pulp.PULP_CBC_CMD(msg=False) # 不显示求解过程
        status = prob.solve(solver)
        
        # 获取结果
        weights_result = [pulp.value(w) if w.value() is not None else 0 for w in weights]
        return weights_result, pulp.LpStatus[status]
    
    # 生成菜品推荐
    def generate_recommendations(self, user_info, dishes, meal_type):
        # 转换菜品格式
        processed_dishes = []
        for dish in dishes:
            try:
                # 转换重量为数值
                weight = float(dish.get("食品克数", 100))
            except:
                weight = 100  # 默认值
                
            processed_dishes.append({
                "name": dish.get("食品名称", "未知菜品"),
                "weight": weight
            })
            
        return self._generate_recommendations(user_info, processed_dishes, meal_type)
    def _generate_recommendations(self, user_info, dishes, meal_type):
        """
        内部方法：生成菜品推荐
        :param user_info: 用户信息
        :param dishes: 已处理的菜品列表 [{"name": "菜品名", "weight": 重量(g)}]
        :param meal_type: 餐别
        :return: 推荐结果字典
        """
        # 计算营养需求
        meal_needs = self.calculate_meal_needs(user_info, meal_type)
        
        # 优化权重
        weights, status = self.optimize_dish_weights(meal_needs, dishes)
        
        # 准备菜品信息列表
        dishes_info = []
        for i, dish in enumerate(dishes):
            nutrition = self.calculate_dish_nutrition(dish)
            dishes_info.append({
                "name": dish["name"],
                "nutrition": nutrition,
                "weight": weights[i]
            })
        
        # 批量生成推荐理由
        reasons_dict = generate_all_dishes_reasons(
            dishes_info, 
            meal_needs, 
            weights,
            user_info,  # 新增用户信息
            meal_type   # 新增餐别
        )
        
        # 准备结果
        results = []
        total_nutrition = defaultdict(float)
        
        for i, dish in enumerate(dishes):
            weight = weights[i]
            nutrition = dishes_info[i]["nutrition"]
            
            # 计算加权营养贡献
            for nut, val in nutrition.items():
                total_nutrition[nut] += val * weight
            
            # 添加菜品结果
            results.append({
                "菜品名称": dish["name"],
                "推荐权重": round(weight, 2),
                "推荐程度": self.weight_to_recommendation(weight),
                "原因": reasons_dict.get(dish["name"], "暂无推荐理由"),
                "营养值": nutrition
            })
        
        # 生成总体推荐
        return {
            "求解状态": status,
            "餐别": meal_type,
            "菜品推荐": results,
            "整餐营养摘要": dict(total_nutrition),
            "用户营养需求": meal_needs
        }
        
    def weight_to_recommendation(self, weight):
        """将权重转换为推荐等级"""
        if weight >= 0.7:
            return "强烈推荐"
        elif weight >= 0.5:
            return "推荐"
        elif weight >= 0.3:
            return "适量食用"
        else:
            return "少量尝试"
            
# 创建优化器实例
dish_optimizer = DishOptimizer()

app_log = setup_logger("logger", "logs/app_log.log")
optimizer_log = setup_logger("optimizer", "logs/optimizer.log")



# 新增API端点
@app.post('/recommend_dishes')
def recommend_dishes():
    """菜品推荐API"""
    json_data = request.get_json()
    app_log.info(f"[Recommend request] {json_data}")
    
    try:
        # 获取用户信息
        user_info = json_data.get("info", {})
        if not user_info:
            return jsonify({"success": False, "error": "缺少用户信息"}), 400
        
        # 获取餐别
        meal_type = json_data.get("data", {}).get("餐别", "午餐")
        app_log.info(f"开始计算餐别 '{meal_type}' 的营养需求")
        app_log.debug(f"用户信息: {user_info}")
        
        # 获取菜品列表
        dish_list = json_data.get("data", {}).get("菜品名称", [])
        app_log.debug(f"菜品数量: {len(dish_list)}")
        
        # 验证菜品格式
        valid_dishes = [d for d in dish_list if validate_dish(d)]
        if len(valid_dishes) != len(dish_list):
            invalid_count = len(dish_list) - len(valid_dishes)
            app_log.warning(f"发现无效菜品格式: {invalid_count}个")
        
        # 生成推荐
        result = dish_optimizer.generate_recommendations(user_info, valid_dishes, meal_type)
        
        return jsonify({
            "success": True,
            "result": result
        })
    
    except Exception as e:
        app_log.error(f"[Recommend error] {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# 原有API端点保持不变
@app.post('/getNutrition')
async def getNutrition():
    # 原有实现保持不变
    pass

if __name__ == "__main__":
    app.run(host='192.168.99.55', port=5000, debug=True, threaded=True)
        
    
    
    
