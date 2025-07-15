import streamlit as st
import requests
import time
import json
import pandas as pd
import numpy as np
from datetime import datetime

# 设置页面配置
st.set_page_config(
    page_title="FoodSky膳食推荐",
    page_icon="🍲",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义CSS样式
st.markdown("""
<style>
    .stApp {
        background-color: #f5f7fa;
    }
    .header {
        background: linear-gradient(135deg, #6a11cb 0%, #2575fc 100%);
        color: white;
        padding: 2rem;
        border-radius: 0 0 20px 20px;
        margin-bottom: 2rem;
    }
    .section {
        background: white;
        border-radius: 15px;
        padding: 1.5rem;
        box-shadow: 0 4px 10px rgba(0,0,0,0.05);
        margin-bottom: 1.5rem;
    }
    .dish-card {
        border: 1px solid #e0e6ed;
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 1rem;
        background: #f9fbfd;
    }
    .recommendation-card {
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 1rem;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    .high-weight {
        background: #d4f7e2;
        border-left: 4px solid #2ecc71;
    }
    .medium-weight {
        background: #fef5e7;
        border-left: 4px solid #f39c12;
    }
    .low-weight {
        background: #fce8e6;
        border-left: 4px solid #e74c3c;
    }
    .submit-btn {
        width: 100%;
        padding: 0.75rem;
        border-radius: 8px;
        background: #3498db;
        color: white;
        font-weight: bold;
        border: none;
        cursor: pointer;
        transition: background 0.3s;
    }
    .submit-btn:hover {
        background: #2980b9;
    }
    .add-btn {
        background: #2ecc71;
        color: white;
        border: none;
        border-radius: 5px;
        padding: 0.5rem 1rem;
        cursor: pointer;
        transition: background 0.3s;
    }
    .add-btn:hover {
        background: #27ae60;
    }
    .remove-btn {
        background: #e74c3c;
        color: white;
        border: none;
        border-radius: 5px;
        padding: 0.25rem 0.75rem;
        cursor: pointer;
        margin-left: 0.5rem;
    }
    .spinner {
        display: inline-block;
        width: 20px;
        height: 20px;
        border: 3px solid rgba(0,0,0,0.1);
        border-radius: 50%;
        border-top-color: #3498db;
        animation: spin 1s linear infinite;
        margin-right: 10px;
    }
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    .nutrient-bar {
        height: 10px;
        border-radius: 5px;
        margin-top: 5px;
        background: #e0e0e0;
    }
    .nutrient-fill {
        height: 100%;
        border-radius: 5px;
        background: #3498db;
    }
    .nutrient-value {
        font-size: 0.9rem;
        margin-top: 3px;
        text-align: right;
    }
</style>
""", unsafe_allow_html=True)

# 应用标题
st.markdown("""
<div class="header">
    <h1 style="text-align:center; margin:0;">🍲FoodSky膳食推荐</h1>
    <p style="text-align:center; margin:0; opacity:0.9;">基于FoodSky，由中科深健研发的食品大模型膳食推荐</p>
</div>
""", unsafe_allow_html=True)

# 后端服务URL
BACKEND_URL = "http://192.168.99.55:5000/recommend_dishes"

# 初始化session state
if 'dishes' not in st.session_state:
    st.session_state.dishes = [{"name": "", "weight": 100.0}]

if 'recommendations' not in st.session_state:
    st.session_state.recommendations = None

if 'request_data' not in st.session_state:
    st.session_state.request_data = None

if 'response_time' not in st.session_state:
    st.session_state.response_time = None

# 添加菜品
def add_dish():
    st.session_state.dishes.append({"name": "", "weight": 100.0})

# 删除菜品
def remove_dish(index):
    if len(st.session_state.dishes) > 1:
        st.session_state.dishes.pop(index)

# 提交表单
def submit_form():
    # 验证用户信息
    required_fields = ['gender', 'age', 'height', 'weight', 'activity_level', 'meal_type']
    if not all([st.session_state.get(field) for field in required_fields]):
        st.error("请填写完整的个人信息")
        return False
    
    # 验证菜品信息
    for i, dish in enumerate(st.session_state.dishes):
        if not dish["name"]:
            st.error(f"菜品 #{i+1} 名称不能为空")
            return False
        if dish["weight"] <= 0:
            st.error(f"菜品 #{i+1} 重量必须大于0")
            return False
    
    return True

# 调用后端服务
def call_backend_service():
    # 准备请求数据
    st.session_state.request_data = {
        "info": {
            "性别": st.session_state.gender,
            "年龄": st.session_state.age,
            "身高": st.session_state.height,
            "体重": st.session_state.weight,
            "activity_level": st.session_state.activity_level
        },
        "data": {
            "餐别": st.session_state.meal_type,
            "菜品名称": [
                {
                    "食品名称": dish["name"],
                    "食品克数": dish["weight"]
                } for dish in st.session_state.dishes
            ]
        }
    }
    
    try:
        # 显示加载状态
        with st.spinner("正在分析您的营养需求，请稍候..."):
            start_time = time.time()
            
            # 发送请求
            response = requests.post(
                BACKEND_URL,
                json=st.session_state.request_data,
                timeout=120  # 120秒超时
            )
            
            end_time = time.time()
            st.session_state.response_time = end_time - start_time
            
            # 检查响应状态
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    st.session_state.recommendations = data["result"]
                    return True
                else:
                    st.error(f"服务返回错误: {data.get('error', '未知错误')}")
            else:
                st.error(f"请求失败, 状态码: {response.status_code}")
                st.error(f"错误信息: {response.text}")
    except requests.exceptions.Timeout:
        st.error("请求超时，请稍后再试")
    except requests.exceptions.ConnectionError:
        st.error("无法连接到后端服务，请检查网络连接")
    except Exception as e:
        st.error(f"发生未知错误: {str(e)}")
    
    return False

# 左侧栏 - 用户信息输入
with st.sidebar:
    st.markdown("### 🧑 个人信息")
    with st.container():
        st.selectbox("性别", ["男", "女"], key="gender", index=0)
        st.number_input("年龄", min_value=1, max_value=120, key="age", value=20)
        st.number_input(
            "身高 (cm)", 
            min_value=50.0, 
            max_value=250.0, 
            key="height", 
            value=175.0,
            step=1.0
        )
        st.number_input(
            "体重 (kg)", 
            min_value=10.0, 
            max_value=200.0, 
            key="weight", 
            value=65.5,
            step=0.1
        )
        st.selectbox(
            "活动水平", 
            ["轻活动水平(办公室工作，很少运动)", "中活动水平(每天适量运动)", "重活动水平(体力劳动或高强度训练)"], 
            key="activity_level",
            index=1
        )
        st.selectbox(
            "餐别", 
            ["早餐", "午餐", "晚餐"], 
            key="meal_type",
            index=1
        )

# 主内容区
col1, col2 = st.columns([1, 1])  # 使用整数作为列宽参数

with col1:
    # 菜品输入部分
    st.markdown("### 🍽️ 菜品信息")
    with st.container():
        for i, dish in enumerate(st.session_state.dishes):
            with st.container():
                with st.container():
                    col_a, col_b = st.columns([3, 1])  # 3和1都是整数
                
                with col_a:
                    dish_name = st.text_input(
                        f"菜品 #{i+1} 名称", 
                        value=dish["name"],
                        key=f"dish_name_{i}",
                        placeholder="例如: 番茄炒蛋"
                    )
                
                with col_b:
                    dish_weight = st.number_input(
                        "重量 (g)", 
                        min_value=1.0, 
                        value=dish["weight"],
                        key=f"dish_weight_{i}",
                        step=1.0
                    )
                
                # 更新session state
                st.session_state.dishes[i]["name"] = dish_name
                st.session_state.dishes[i]["weight"] = dish_weight
                
                # 删除按钮（不是第一个菜品时显示）
                if i > 0:
                    st.button("删除", key=f"remove_{i}", on_click=remove_dish, args=(i,))
        
        # 添加菜品按钮
        st.button("➕ 添加菜品", on_click=add_dish, use_container_width=True)
        
        # 提交按钮
        if st.button("生成菜品推荐", use_container_width=True, type="primary"):
            if submit_form():
                if call_backend_service():
                    st.success("推荐结果已生成！")
                else:
                    st.session_state.recommendations = None

with col2:
    # 结果显示部分
    st.markdown("### 📊 推荐结果")
    
    if st.session_state.recommendations:
        recommendations = st.session_state.recommendations
        
        # 显示请求信息
        st.caption(f"请求时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 响应时间: {st.session_state.response_time:.2f}秒")
        
        # 显示餐别和求解状态
        st.markdown(f"**餐别**: {recommendations.get('餐别', '午餐')}")
        st.markdown(f"**求解状态**: {recommendations.get('求解状态', '未知')}")
        
        # 显示菜品推荐
        st.markdown("### 菜品推荐")
        
        # 创建选项卡
        tab1, tab2 = st.tabs(["推荐详情", "营养分析"])
        
        with tab1:
            for dish in recommendations.get("菜品推荐", []):
                weight = dish.get("推荐权重", 0)
                
                # 根据权重设置样式
                if weight >= 0.7:
                    card_class = "high-weight"
                    recommendation_text = "强烈推荐"
                elif weight >= 0.5:
                    card_class = "medium-weight"
                    recommendation_text = "推荐"
                elif weight >= 0.3:
                    card_class = "medium-weight"
                    recommendation_text = "适量食用"
                else:
                    card_class = "low-weight"
                    recommendation_text = "少量尝试"
                
                with st.container():
                    st.markdown(f"<div class='recommendation-card {card_class}'>", unsafe_allow_html=True)
                    
                    # 菜品名称和权重
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"#### {dish.get('菜品名称', '未知菜品')}")
                    with col2:
                        st.markdown(f"**权重**: {weight:.2f} ({recommendation_text})")
                    
                    # 推荐原因
                    st.markdown(f"**原因**: {dish.get('原因', '暂无推荐理由')}")
                    
                    # 营养值摘要
                    with st.expander("查看营养详情"):
                        nutrition = dish.get("营养值", {})
                        if nutrition:
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("能量", f"{nutrition.get('能量', 0):.1f} kcal")
                                st.metric("蛋白质", f"{nutrition.get('蛋白质', 0):.1f} g")
                            with col2:
                                st.metric("脂肪", f"{nutrition.get('脂肪', 0):.1f} g")
                                st.metric("碳水化合物", f"{nutrition.get('碳水化合物', 0):.1f} g")
                            with col3:
                                st.metric("钠", f"{nutrition.get('钠', 0):.1f} mg")
                                st.metric("维生素C", f"{nutrition.get('维生素C', 0):.1f} mg")
                        else:
                            st.warning("无营养数据")
                    
                    st.markdown("</div>", unsafe_allow_html=True)
        
        with tab2:
            # 整餐营养摘要
            total_nutrition = recommendations.get("整餐营养摘要", {})
            if total_nutrition:
                st.markdown("### 整餐营养摘要")
                
                # 创建营养指标卡片
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("总能量", f"{total_nutrition.get('能量', 0):.1f} kcal")
                    st.metric("总蛋白质", f"{total_nutrition.get('蛋白质', 0):.1f} g")
                with col2:
                    st.metric("总脂肪", f"{total_nutrition.get('脂肪', 0):.1f} g")
                    st.metric("总碳水化合物", f"{total_nutrition.get('碳水化合物', 0):.1f} g")
                with col3:
                    st.metric("总钠", f"{total_nutrition.get('钠', 0):.1f} mg")
                    st.metric("总维生素C", f"{total_nutrition.get('维生素C', 0):.1f} mg")
                
                # 营养分布图表
                st.markdown("### 营养分布")
                
                # 主要营养素
                main_nutrients = ["能量", "蛋白质", "脂肪", "碳水化合物"]
                main_values = [total_nutrition.get(n, 0) for n in main_nutrients]
                
                # 创建DataFrame
                df = pd.DataFrame({
                    "营养素": main_nutrients,
                    "含量": main_values
                })
                
                # 显示柱状图
                st.bar_chart(df.set_index("营养素"))
                
                # 微量营养素
                micro_nutrients = ["钙", "铁", "维生素A", "维生素C", "钠"]
                micro_values = [total_nutrition.get(n, 0) for n in micro_nutrients]
                
                # 显示微量营养素
                st.markdown("### 微量营养素")
                for nutrient, value in zip(micro_nutrients, micro_values):
                    st.markdown(f"**{nutrient}**: {value:.1f}")
                    # 添加简单的进度条
                    max_value = max(micro_values) * 1.1 if max(micro_values) > 0 else 100
                    percent = min(value / max_value, 1.0) if max_value > 0 else 0
                    st.markdown(f"""
                    <div class="nutrient-bar">
                        <div class="nutrient-fill" style="width: {percent*100}%;"></div>
                    </div>
                    <div class="nutrient-value">{value:.1f}</div>
                    """, unsafe_allow_html=True)
            else:
                st.warning("无整餐营养摘要数据")
    else:
        st.info("请填写左侧表单并点击'生成菜品推荐'按钮获取个性化推荐")

# 添加一些说明
st.markdown("---")
st.markdown("""
### 使用说明
1. 在左侧填写您的个人信息（性别、年龄、身高、体重等）
2. 添加您想评估的菜品（至少一个）
3. 点击"生成菜品推荐"按钮获取个性化推荐
4. 查看右侧的推荐结果，了解每道菜的推荐程度和原因

**推荐权重说明**:
- **强烈推荐 (权重 ≥ 0.7)**: 营养均衡且符合需求
- **推荐 (0.5 ≤ 权重 < 0.7)**: 营养良好，适合食用
- **适量食用 (0.3 ≤ 权重 < 0.5)**: 可以少量食用
- **少量尝试 (权重 < 0.3)**: 建议本餐避免或少量尝试
""")

# 调试信息（可选）
if st.checkbox("显示调试信息"):
    st.markdown("### 请求数据")
    st.json(st.session_state.request_data)
    
    if st.session_state.recommendations:
        st.markdown("### 完整响应")
        st.json(st.session_state.recommendations)