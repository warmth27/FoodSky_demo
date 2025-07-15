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
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .recommendation-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
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
        transition: width 0.5s;
    }
    .nutrient-value {
        font-size: 12px;
        margin-bottom: 10px;
    }
    .nutrition-range {
        font-size: 12px;
        color: #666;
        margin-top: -5px;
    }
    .summary-card {
        background: linear-gradient(145deg, #f5f5f5, #e0e0e0);
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 15px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .dish-input-row {
        display: flex;
        margin-bottom: 15px;
        align-items: center;
    }
    .dish-input-cell {
        margin-right: 15px;
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

# 营养单位映射
NUTRIENT_UNITS = {
    "能量": "kcal",
    "蛋白质": "g",
    "脂肪": "g",
    "碳水化合物": "g",
    "钠": "mg",
    "钙": "mg",
    "铁": "mg",
    "维生素C": "mg",
    "维生素A": "μg",
    "维生素B1": "mg",
    "维生素B2": "mg",
    "烟酸": "mg",
    "锌": "mg",
    "膳食纤维": "g"
}

# 初始化session state
if 'dishes' not in st.session_state:
    st.session_state.dishes = [{"name": "", "weight": 100.0}]
if 'recommendations' not in st.session_state:
    st.session_state.recommendations = None
if 'request_data' not in st.session_state:
    st.session_state.request_data = None
if 'response_time' not in st.session_state:
    st.session_state.response_time = None
if 'selected_dish' not in st.session_state:
    st.session_state.selected_dish = None

# 添加菜品
def add_dish():
    st.session_state.dishes.append({"name": "", "weight": 100.0})

# 删除菜品
def remove_dish(index):
    if len(st.session_state.dishes) > 1:
        st.session_state.dishes.pop(index)
        st.rerun()

# 活动水平映射
ACTIVITY_MAPPING = {
    "轻活动水平(办公室工作，很少运动)": "a",
    "中活动水平(每天适量运动)": "b",
    "重活动水平(体力劳动或高强度训练)": "c"
}

# 提交表单
def submit_form():
    required_fields = ['gender', 'age', 'height', 'weight', 'activity_level_label', 'meal_type']
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
    # 映射活动水平为简写形式
    activity_level = ACTIVITY_MAPPING[st.session_state.activity_level_label]
    
    st.session_state.request_data = {
        "info": {
            "性别": st.session_state.gender,
            "年龄": st.session_state.age,
            "身高": st.session_state.height,
            "体重": st.session_state.weight,
            "activity_level": activity_level
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

# 渲染营养需求卡
def render_nutrition_card(title, value, range_value, unit):
    if isinstance(range_value, (tuple, list)):
        range_str = f"{range_value[0]:.0f}-{range_value[1]:.0f}{unit}"
    else:
        range_str = f"{range_value:.0f}{unit}"
    
    return f"""
    <div class="summary-card">
        <h4>{title}</h4>
        <div class="nutrient-bar">
            <div class="nutrient-fill" style="width: {min(value / (range_value[1] if isinstance(range_value, tuple) else range_value), 1) * 100}%"></div>
        </div>
        <div class="nutrient-value">当前: {value:.0f}{unit} <span class="nutrition-range">需求: {range_str}</span></div>
    </div>
    """

# 左侧栏 - 用户信息输入
with st.sidebar:
    st.markdown("### 🧑 个人信息")
    st.selectbox("性别", ["男", "女"], key="gender", index=0)
    st.number_input("年龄", min_value=1, max_value=120, key="age", value=20)
    st.number_input("身高 (cm)", min_value=50.0, max_value=250.0, key="height", value=175.0, step=1.0)
    st.number_input("体重 (kg)", min_value=10.0, max_value=200.0, key="weight", value=65.5, step=0.5)
    
    selected_activity_label = st.selectbox(
        "活动水平",
        list(ACTIVITY_MAPPING.keys()),
        key="activity_level_label",
        index=1
    )
    
    st.selectbox("餐别", ["早餐", "午餐", "晚餐"], key="meal_type", index=1)

# 主内容区
main_container = st.container()

with main_container:
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown("### 🍽️ 菜品信息")
        
        for i, dish in enumerate(st.session_state.dishes):
            st.markdown(f"**菜品 #{i+1}**")
            st.text_input("菜品名称", value=dish["name"], 
                         key=f"dish_name_{i}", 
                         placeholder="例如: 番茄炒蛋",
                         label_visibility="collapsed")
            
            weight_col, remove_col = st.columns([3, 1])
            with weight_col:
                dish["weight"] = st.number_input("重量 (g)", min_value=1.0, 
                                               value=dish["weight"], 
                                               key=f"dish_weight_{i}", 
                                               step=1.0)
            with remove_col:
                if i > 0:
                    if st.button("删除", key=f"remove_{i}", use_container_width=True):
                        remove_dish(i)
                        st.stop()
            
            st.divider()
        
        # 添加按钮和生成推荐
        st.button("➕ 添加菜品", on_click=add_dish, use_container_width=True)
        if st.button("✨ 生成菜品推荐", type="primary", use_container_width=True):
            if submit_form():
                if call_backend_service():
                    st.toast("推荐结果已生成！", icon="✅")
                else:
                    st.session_state.recommendations = None
                    st.toast("推荐生成失败，请检查错误信息", icon="⚠️")

# 推荐结果显示
if st.session_state.recommendations:
    recommendations = st.session_state.recommendations
    with col2:
        st.markdown("### 📊 推荐结果")
        st.caption(f"请求时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 响应时间: {st.session_state.response_time:.2f}秒")
        
        # 基本信息卡片
        with st.expander("📋 基本信息摘要", expanded=True):
            col_summary1, col_summary2 = st.columns(2)
            with col_summary1:
                st.metric("餐别", recommendations.get("餐别", "午餐"))
                st.metric("状态", recommendations.get("求解状态", "未知"))
            with col_summary2:
                st.metric("活动水平", st.session_state.activity_level_label)
                st.metric("能量需求范围", 
                         f"{recommendations.get('用户营养需求', {}).get('能量', [0,0])[0]:.0f}-"
                         f"{recommendations.get('用户营养需求', {}).get('能量', [0,0])[1]:.0f} kcal")
        
        tab_rec, tab_nutrition, tab_details = st.tabs(["菜品推荐", "营养分析", "详情数据"])
        
        with tab_rec:
            st.markdown("#### 📋 菜品推荐列表")
            
            # 排序：按权重降序
            sorted_dishes = sorted(recommendations.get("菜品推荐", []), 
                                  key=lambda x: x.get("推荐权重", 0), 
                                  reverse=True)
            
            for dish in sorted_dishes:
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
                    
                    cols = st.columns([3, 2])
                    with cols[0]:
                        st.markdown(f"#### 🍲 {dish.get('菜品名称', '未知菜品')}")
                        st.markdown(f"**推荐指数**: {weight:.2f} ({recommendation_text})")
                    with cols[1]:
                        st.progress(min(weight, 1.0), text=f"{recommendation_text}")
                    
                    st.markdown(f"##### 🧠 推荐理由")
                    st.caption(f"{dish.get('原因', '暂无推荐理由')}")
                    
                    nutrition = dish.get("营养值", {})
                    if nutrition:
                        with st.expander("📊 营养成分分析", expanded=False):
                            st.markdown("**主要营养素**")
                            col_nut1, col_nut2, col_nut3 = st.columns(3)
                            with col_nut1:
                                st.metric("能量", f"{nutrition.get('能量', 0):.1f} kcal")
                                st.metric("蛋白质", f"{nutrition.get('蛋白质', 0):.1f} g")
                            with col_nut2:
                                st.metric("脂肪", f"{nutrition.get('脂肪', 0):.1f} g")
                                st.metric("碳水化合物", f"{nutrition.get('碳水化合物', 0):.1f} g")
                            with col_nut3:
                                st.metric("钠", f"{nutrition.get('钠', 0):.1f} mg")
                                st.metric("维生素C", f"{nutrition.get('维生素C', 0):.1f} mg")
                    
                    st.markdown("</div>", unsafe_allow_html=True)
        
        with tab_nutrition:
            st.markdown("#### 📊 营养分析")
            
            user_needs = recommendations.get("用户营养需求", {})
            total_nutrition = recommendations.get("整餐营养摘要", {})
            
            if total_nutrition and user_needs:
                st.markdown("##### 🍽️ 整餐营养摘要")
                col_sum1, col_sum2 = st.columns(2)
                
                with col_sum1:
                    st.metric("总能量", f"{total_nutrition.get('能量', 0):.1f} kcal", 
                             delta=f"{recommendations['用户营养需求'].get('能量', [0,0])[0]:.1f}-{recommendations['用户营养需求'].get('能量', [0,0])[1]:.1f} kcal",
                             delta_color="off")
                    st.metric("总蛋白质", f"{total_nutrition.get('蛋白质', 0):.1f} g",
                             delta=f"{recommendations['用户营养需求'].get('蛋白质', [0,0])[0]:.1f}-{recommendations['用户营养需求'].get('蛋白质', [0,0])[1]:.1f} g",
                             delta_color="off")
                with col_sum2:
                    st.metric("总脂肪", f"{total_nutrition.get('脂肪', 0):.1f} g",
                             delta=f"{recommendations['用户营养需求'].get('脂肪', [0,0])[0]:.1f}-{recommendations['用户营养需求'].get('脂肪', [0,0])[1]:.1f} g",
                             delta_color="off")
                    st.metric("总碳水", f"{total_nutrition.get('碳水化合物', 0):.1f} g",
                             delta=f"{recommendations['用户营养需求'].get('碳水化合物', [0,0])[0]:.1f}-{recommendations['用户营养需求'].get('碳水化合物', [0,0])[1]:.1f} g",
                             delta_color="off")
                
                st.markdown("---")
                st.markdown("##### 📈 营养素满足情况")
                
                # 宏量营养素分析
                st.markdown("**宏量营养素**")
                col_macronutrients = st.columns(2)
                with col_macronutrients[0]:
                    st.markdown(render_nutrition_card(
                        "能量", 
                        total_nutrition.get('能量', 0),
                        user_needs.get('能量', [0, 0]),
                        "kcal"
                    ), unsafe_allow_html=True)
                    
                    st.markdown(render_nutrition_card(
                        "蛋白质", 
                        total_nutrition.get('蛋白质', 0),
                        user_needs.get('蛋白质', [0, 0]),
                        "g"
                    ), unsafe_allow_html=True)
                    
                with col_macronutrients[1]:
                    st.markdown(render_nutrition_card(
                        "脂肪", 
                        total_nutrition.get('脂肪', 0),
                        user_needs.get('脂肪', [0, 0]),
                        "g"
                    ), unsafe_allow_html=True)
                    
                    st.markdown(render_nutrition_card(
                        "碳水化合物", 
                        total_nutrition.get('碳水化合物', 0),
                        user_needs.get('碳水化合物', [0, 0]),
                        "g"
                    ), unsafe_allow_html=True)
                
                # 微量营养素分析
                st.markdown("**微量营养素**")
                col_micronutrients = st.columns(2)
                with col_micronutrients[0]:
                    st.markdown(render_nutrition_card(
                        "钠", 
                        total_nutrition.get('钠', 0),
                        user_needs.get('钠', [0, 0]) if isinstance(user_needs.get('钠'), (list, tuple)) else user_needs.get('钠', 0),
                        "mg"
                    ), unsafe_allow_html=True)
                    
                    st.markdown(render_nutrition_card(
                        "钙", 
                        total_nutrition.get('钙', 0),
                        user_needs.get('钙', [0, 0]) if isinstance(user_needs.get('钙'), (list, tuple)) else user_needs.get('钙', 0),
                        "mg"
                    ), unsafe_allow_html=True)
                    
                with col_micronutrients[1]:
                    st.markdown(render_nutrition_card(
                        "铁", 
                        total_nutrition.get('铁', 0),
                        user_needs.get('铁', [0, 0]) if isinstance(user_needs.get('铁'), (list, tuple)) else user_needs.get('铁', 0),
                        "mg"
                    ), unsafe_allow_html=True)
                    
                    st.markdown(render_nutrition_card(
                        "维生素C", 
                        total_nutrition.get('维生素C', 0),
                        user_needs.get('维生素C', [0, 0]) if isinstance(user_needs.get('维生素C'), (list, tuple)) else user_needs.get('维生素C', 0),
                        "mg"
                    ), unsafe_allow_html=True)
                
                # 营养分布图表
                st.markdown("---")
                st.markdown("##### 📊 营养分布")
                
                main_nutrients = ["能量", "蛋白质", "脂肪", "碳水化合物"]
                main_values = [total_nutrition.get(n, 0) for n in main_nutrients]
                df_main = pd.DataFrame({
                    "营养素": main_nutrients,
                    "含量": main_values,
                    "单位": [NUTRIENT_UNITS.get(n, "") for n in main_nutrients]
                })
                st.bar_chart(df_main.set_index("营养素")["含量"])
                
                st.markdown("**维生素分布**")
                vitamin_nutrients = ["维生素A", "维生素B1", "维生素B2", "维生素C"]
                vitamin_values = [total_nutrition.get(n, 0) for n in vitamin_nutrients]
                df_vitamin = pd.DataFrame({
                    "维生素": vitamin_nutrients,
                    "含量": vitamin_values,
                    "单位": [NUTRIENT_UNITS.get(n, "") for n in vitamin_nutrients]
                })
                st.bar_chart(df_vitamin.set_index("维生素")["含量"])
                
                st.markdown("**矿物质分布**")
                mineral_nutrients = ["钠", "钙", "铁", "锌"]
                mineral_values = [total_nutrition.get(n, 0) for n in mineral_nutrients]
                df_mineral = pd.DataFrame({
                    "矿物质": mineral_nutrients,
                    "含量": mineral_values,
                    "单位": [NUTRIENT_UNITS.get(n, "") for n in mineral_nutrients]
                })
                st.bar_chart(df_mineral.set_index("矿物质")["含量"])
        
        with tab_details:
            st.markdown("#### 📊 详情数据")
            
            st.markdown("##### 用户需求营养范围")
            if recommendations.get("用户营养需求"):
                df_needs = pd.DataFrame.from_dict(recommendations["用户营养需求"], orient="index", columns=["值"])
                st.dataframe(df_needs, use_container_width=True)
            else:
                st.warning("无用户营养需求数据")
            
            st.markdown("##### 菜品推荐详情")
            if recommendations.get("菜品推荐"):
                dish_data = []
                for dish in recommendations["菜品推荐"]:
                    dish_data.append({
                        "菜品名称": dish.get("菜品名称", ""),
                        "推荐权重": dish.get("推荐权重", 0),
                        "原因": dish.get("原因", "")
                    })
                st.dataframe(pd.DataFrame(dish_data), use_container_width=True)
            else:
                st.warning("无菜品推荐数据")
            
            st.markdown("##### 整餐营养摘要")
            if recommendations.get("整餐营养摘要"):
                df_total = pd.DataFrame.from_dict(recommendations["整餐营养摘要"], orient="index", columns=["值"])
                st.dataframe(df_total, use_container_width=True)
            else:
                st.warning("无整餐营养摘要数据")
else:
    with col2:
        st.info("✨ 请填写左侧表单并点击'生成菜品推荐'按钮获取个性化推荐")

# 使用说明
st.markdown("---")
with st.expander("ℹ️ 使用说明"):
    st.markdown("""
    ### 使用指南
    
    1. **填写个人信息**：
       - 在左侧栏完整填写您的性别、年龄、身高、体重等信息
       - 选择您的活动水平（根据日常活动强度）
       - 选择要规划的餐别（早餐/午餐/晚餐）
    
    2. **添加菜品信息**：
       - 输入菜品名称（如：番茄炒蛋）
       - 设置菜品份量（克数）
       - 可添加多个菜品进行混合分析
    
    3. **生成推荐**：
       - 点击"✨ 生成菜品推荐"按钮进行分析
       - 系统将根据您的个人情况和菜品特点生成推荐
    
    4. **查看结果**：
       - 在右侧推荐结果区域查看分析结果
       - 通过三个标签页分别查看：
         - 📋 菜品推荐 - 各菜品推荐指数及原因
         - 📊 营养分析 - 整餐营养构成及需求满足情况
         - 📊 详情数据 - 详细的数据表格
    """)
    
    st.markdown("### 推荐权重说明")
    cols_legend = st.columns(4)
    with cols_legend[0]:
        st.markdown("<div class='recommendation-card high-weight'><b>强烈推荐</b><br>(权重 ≥ 0.7)</div>", unsafe_allow_html=True)
    with cols_legend[1]:
        st.markdown("<div class='recommendation-card medium-weight'><b>推荐</b><br>(0.5 ≤ 权重 < 0.7)</div>", unsafe_allow_html=True)
    with cols_legend[2]:
        st.markdown("<div class='recommendation-card medium-weight'><b>适量食用</b><br>(0.3 ≤ 权重 < 0.5)</div>", unsafe_allow_html=True)
    with cols_legend[3]:
        st.markdown("<div class='recommendation-card low-weight'><b>少量尝试</b><br>(权重 < 0.3)</div>", unsafe_allow_html=True)

# 调试信息（可选）
if st.checkbox("显示调试信息"):
    st.markdown("### 请求数据")
    st.json(st.session_state.request_data)
    
    if st.session_state.recommendations:
        st.markdown("### 完整响应")
        st.json(st.session_state.recommendations)