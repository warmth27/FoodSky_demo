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
    

