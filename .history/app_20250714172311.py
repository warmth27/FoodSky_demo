import streamlit as st
import requests
import time
import json
import pandas as pd
import numpy as np
from datetime import datetime

# 设置页面配置
st.set_page_config(
    page_title="智能菜品推荐系统",
    page_icon="🍲",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义CSS样式
st.markdown("""
<style>
    .recommendation-card {
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 15px;
        margin-bottom: 10px;
        background-color: #fafafa;
    }
    .high-weight {
        border-left: 6px solid #4CAF50;
    }
    .medium-weight {
        border-left: 6px solid #FFC107;
    }
    .low-weight {
        border-left: 6px solid #F44336;
    }
    .nutrient-bar {
        height: 10px;
        background-color: #f0f0f0;
        border-radius: 5px;
        overflow: hidden;
        margin-bottom: 4px;
    }
    .nutrient-fill {
        height: 100%;
        background-color: #4CAF50;
    }
    .nutrient-value {
        font-size: 12px;
        margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# 应用标题
st.markdown("""
<div class="header">
    <h1 style="text-align:center; margin:0;">🍲 智能菜品推荐系统</h1>
    <p style="text-align:center; margin:0; opacity:0.9;">基于营养学与AI的个性化菜品推荐</p>
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
    required_fields = ['gender', 'age', 'height', 'weight', 'activity_level', 'meal_type']
    if not all([st.session_state.get(field) for field in required_fields]):
        st.error("请填写完整的个人信息")
        return False
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
        with st.spinner("正在分析您的营养需求，请稍候..."):
            start_time = time.time()
            response = requests.post(BACKEND_URL, json=st.session_state.request_data, timeout=120)
            end_time = time.time()
            st.session_state.response_time = end_time - start_time

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
    st.selectbox("性别", ["男", "女"], key="gender", index=0)
    st.number_input("年龄", min_value=1, max_value=120, key="age", value=20)
    st.number_input("身高 (cm)", min_value=50.0, max_value=250.0, key="height", value=175.0, step=1.0)
    st.number_input("体重 (kg)", min_value=10.0, max_value=200.0, key="weight", value=65.5, step=0.)
    
    # 活动水平映射
    activity_options = {
        "轻活动水平(办公室工作，很少运动)": "a",
        "中活动水平(每天适量运动)": "b",
        "重活动水平(体力劳动或高强度训练)": "c"
    }
    selected_activity_label = st.selectbox(
        "活动水平",
        list(activity_options.keys()),
        key="activity_level_label",
        index=1
    )
    # 将选择的值映射为简写形式
    st.session_state.activity_level = activity_options[selected_activity_label]
    
    st.selectbox("餐别", ["早餐", "午餐", "晚餐"], key="meal_type", index=1)

# 主内容区
main_container = st.container()

with main_container:
    col1, col2 = st.columns([1, 1])
    st.markdown("### 🍽️ 菜品信息")

    for i, dish in enumerate(st.session_state.dishes):
        col_name, col_weight, col_remove = st.columns([3, 1, 0.5])

        with col_name:
            name = st.text_input(f"菜品 #{i+1} 名称", value=dish["name"], key=f"dish_name_{i}", placeholder="例如: 番茄炒蛋")
        with col_weight:
            weight = st.number_input("重量 (g)", min_value=1.0, value=dish["weight"], key=f"dish_weight_{i}", step=1.0)
        with col_remove:
            if i > 0:
                if st.button("删除", key=f"remove_{i}"):
                    remove_dish(i)
                    st.experimental_rerun()

        st.session_state.dishes[i]["name"] = name
        st.session_state.dishes[i]["weight"] = weight

    # 添加按钮和生成推荐
    st.button("➕ 添加菜品", on_click=add_dish)
    if st.button("生成菜品推荐"):
        if submit_form():
            if call_backend_service():
                st.success("推荐结果已生成！")
            else:
                st.session_state.recommendations = None

    with col2:
        st.markdown("### 📊 推荐结果")
        if st.session_state.recommendations:
            recommendations = st.session_state.recommendations
            st.caption(f"请求时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 响应时间: {st.session_state.response_time:.2f}秒")
            st.markdown(f"**餐别**: {recommendations.get('餐别', '午餐')}")
            st.markdown(f"**求解状态**: {recommendations.get('求解状态', '未知')}")
            st.markdown("### 菜品推荐")
            tab1, tab2 = st.tabs(["推荐详情", "营养分析"])

            with tab1:
                for dish in recommendations.get("菜品推荐", []):
                    weight = dish.get("推荐权重", 0)
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
                        st.markdown(f"#### {dish.get('菜品名称', '未知菜品')}")
                        st.markdown(f"**权重**: {weight:.2f} ({recommendation_text})")
                        st.markdown(f"**原因**: {dish.get('原因', '暂无推荐理由')}")
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
                total_nutrition = recommendations.get("整餐营养摘要", {})
                if total_nutrition:
                    st.markdown("### 整餐营养摘要")
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

                    st.markdown("### 营养分布")
                    main_nutrients = ["能量", "蛋白质", "脂肪", "碳水化合物"]
                    main_values = [total_nutrition.get(n, 0) for n in main_nutrients]
                    df = pd.DataFrame({"营养素": main_nutrients, "含量": main_values})
                    st.bar_chart(df.set_index("营养素"))

                    micro_nutrients = ["钙", "铁", "维生素A", "维生素C", "钠"]
                    micro_values = [total_nutrition.get(n, 0) for n in micro_nutrients]
                    st.markdown("### 微量营养素")
                    for nutrient, value in zip(micro_nutrients, micro_values):
                        st.markdown(f"**{nutrient}**: {value:.1f}")
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

# 使用说明
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
