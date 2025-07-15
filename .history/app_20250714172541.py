import streamlit as st
import requests
import time
import json
import pandas as pd
from datetime import datetime

# 页面配置
st.set_page_config(
    page_title="智能菜品推荐系统",
    page_icon="🍲",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 标题
st.title("🍲 智能菜品推荐系统")
st.markdown("基于营养学与AI的个性化菜品推荐")

# 后端地址
BACKEND_URL = "http://192.168.99.55:5000/recommend_dishes"

# Session 初始化
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

# 表单验证
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

# 调用后端
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
            response = requests.post(
                BACKEND_URL,
                json=st.session_state.request_data,
                timeout=120
            )
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
    except Exception as e:
        st.error(f"请求错误: {e}")
    return False

# 左侧输入
with st.sidebar:
    st.header("🧑 个人信息")
    st.selectbox("性别", ["男", "女"], key="gender")
    st.number_input("年龄", min_value=1, max_value=120, key="age", value=25)
    st.number_input("身高 (cm)", min_value=50.0, max_value=250.0, key="height", value=170.0)
    st.number_input("体重 (kg)", min_value=10.0, max_value=200.0, key="weight", value=60.0)
    st.selectbox("活动水平", [
        "轻活动水平(办公室工作，很少运动)",
        "中活动水平(每天适量运动)",
        "重活动水平(体力劳动或高强度训练)"
    ], key="activity_level")
    st.selectbox("餐别", ["早餐", "午餐", "晚餐"], key="meal_type")

# 菜品输入部分
st.subheader("🍽️ 菜品信息")
for i, dish in enumerate(st.session_state.dishes):
    col_name, col_weight, col_del = st.columns([3, 2, 1])
    with col_name:
        name = st.text_input(f"菜品 #{i+1}", value=dish["name"], key=f"dish_name_{i}", placeholder="例如：番茄炒蛋")
    with col_weight:
        weight = st.number_input("重量(g)", value=dish["weight"], key=f"dish_weight_{i}", min_value=1.0, step=1.0)
    with col_del:
        if i > 0 and st.button("删除", key=f"del_{i}"):
            remove_dish(i)
            st.experimental_rerun()
    st.session_state.dishes[i]["name"] = name
    st.session_state.dishes[i]["weight"] = weight

if st.button("➕ 添加菜品"):
    add_dish()
    st.experimental_rerun()

if st.button("生成菜品推荐"):
    if submit_form():
        if call_backend_service():
            st.success("推荐结果已生成！")
        else:
            st.session_state.recommendations = None

# 推荐结果展示
if st.session_state.recommendations:
    rec = st.session_state.recommendations
    st.markdown("---")
    st.subheader("📊 推荐结果")
    st.caption(f"请求时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 响应耗时: {st.session_state.response_time:.2f} 秒")
    st.markdown(f"**餐别**: {rec.get('餐别', '午餐')}  |  **求解状态**: {rec.get('求解状态', '未知')}")

    tab1, tab2 = st.tabs(["推荐详情", "营养分析"])

    with tab1:
        for dish in rec.get("菜品推荐", []):
            name = dish.get("菜品名称", "未知")
            weight = dish.get("推荐权重", 0)
            reason = dish.get("原因", "无推荐理由")
            st.markdown(f"### {name}")
            st.markdown(f"**推荐权重**: {weight:.2f}")
            st.markdown(f"**推荐理由**: {reason}")
            with st.expander("营养详情"):
                nutrition = dish.get("营养值", {})
                for key, value in nutrition.items():
                    st.write(f"{key}: {value}")

    with tab2:
        st.subheader("整餐营养摘要")
        nutrition = rec.get("整餐营养摘要", {})
        if nutrition:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("总能量", f"{nutrition.get('能量', 0):.1f} kcal")
                st.metric("总蛋白质", f"{nutrition.get('蛋白质', 0):.1f} g")
            with col2:
                st.metric("总脂肪", f"{nutrition.get('脂肪', 0):.1f} g")
                st.metric("总碳水化合物", f"{nutrition.get('碳水化合物', 0):.1f} g")
            with col3:
                st.metric("总钠", f"{nutrition.get('钠', 0):.1f} mg")
                st.metric("总维生素C", f"{nutrition.get('维生素C', 0):.1f} mg")

            st.markdown("### 营养分布图")
            keys = ["能量", "蛋白质", "脂肪", "碳水化合物"]
            values = [nutrition.get(k, 0) for k in keys]
            df = pd.DataFrame({"营养素": keys, "含量": values})
            st.bar_chart(df.set_index("营养素"))

            st.markdown("### 微量营养素")
            micronutrients = ["钙", "铁", "维生素A", "维生素C", "钠"]
            for k in micronutrients:
                v = nutrition.get(k, 0.0)
                st.write(f"**{k}**: {v:.1f}")
        else:
            st.warning("无整餐营养数据")

# 调试信息（可选）
if st.checkbox("显示调试信息"):
    st.json(st.session_state.request_data)
    st.json(st.session_state.recommendations)
