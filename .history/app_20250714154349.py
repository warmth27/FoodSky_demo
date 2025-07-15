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

# 自定义CSS样式（保持不变）
st.markdown("""
<style>
    /* 保留所有CSS样式 */
</style>
""", unsafe_allow_html=True)

# 应用标题（保持不变）
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
            retu