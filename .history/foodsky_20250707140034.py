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
