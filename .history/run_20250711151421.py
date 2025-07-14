import requests    
test_data = {
        "flag": 0, 
        "info": {
            '性别': "男",
            '年龄': 20,
            '身高': 175,
            '体重': 65.5,
            'activity_level': "b",
            '疾病情况': None
        },
        "data": {
            "餐别":"午餐",
            '菜品名称':[
                {
                   "食品名称":"番茄炒蛋",
                    "食品克数":"200",
                    "食材信息": {}
                },
                {
                   "食品名称":"凉拌土豆丝",
                    "食品克数": "100",
                    "食材信息": {
                        "土豆":"100"
                        }
                },
                {
                   "食品名称":"尖椒土豆片",
                    "食品克数":"200",
                    "食材信息": {}
                },
                {
                   "食品名称":"裙带菜豆腐汤",
                    "食品克数": "100",
                    "食材信息": {}
                },
                {
                   "食品名称":"白扁豆炒肉",
                    "食品克数":"200",
                    "食材信息": {}
                },
                {
                   "食品名称":"葛根排骨汤",
                    "食品克数": "100",
                    "食材信息": {}
                },
                {
                   "食品名称":"红烧带鱼",
                    "食品克数":"200",
                    "食材信息": {}
                },
                {
                   "食品名称":"卤蛋",
                    "食品克数": "50",
                    "食材信息": {
                        "鸡蛋":"50"
                        }
                },
                {
                   "食品名称":"牛肉炒木耳",
                    "食品克数":"200",
                    "食材信息": {}
                },
                {
                   "食品名称":"素炒甘蓝丝",
                    "食品克数": "100",
                    "食材信息": {
                        "结球甘蓝":"100"
                        }
                },
                {
                   "食品名称":"尖椒炒肉",
                    "食品克数":"100",
                    "食材信息": {}
                },
                {
                   "食品名称":"蒸芋头",
                    "食品克数": "100",
                    "食材信息": {
                        "芋头":"100"
                        }
                },
                {
                   "食品名称":"猪肉白菜炖粉条",
                    "食品克数":"200",
                    "食材信息": {}
                },
                {
                   "食品名称":"煮鹅蛋",
                    "食品克数": "70",
                    "食材信息": {
                        "鹅蛋":"70"
                        }
                }
                
            
            ] 
        }
        }
ip_address = 'http://192.168.99.55'
port = '5000'
url = f"{ip_address}:{port}/recommend_dishes"
try:
    start_time = time.time()
    
    # 设置超时和异常处理
    response = requests.post(url, json=test_data, timeout=120)
    
    end_time = time.time()
    print(f"请求耗时: {end_time - start_time:.2f}秒")
    
    if response.status_code == 200:
        result = response.json()
        if result.get('success'):
            print("推荐结果获取成功！")
            # 简略打印重要结果
            recommendations = result['result']['菜品推荐']
            print(f"\n餐别: {result['result']['餐别']}")
            print("="*50)
            for dish in recommendations:
                print(f"菜品: {dish['菜品名称']}")
                print(f"权重: {dish['推荐权重']:.2f} ({dish['推荐程度']})")
                print(f"原因: {dish['原因']}")
                print("-"*50)
        else:
            print(f"服务返回错误: {result.get('error', '未知错误')}")
    else:
        print(f"请求失败, 状态码: {response.status_code}")
        print(f"错误信息: {response.text}")

except requests.exceptions.Timeout:
    print("请求超时，可能是菜品数量过多或服务器繁忙")
except requests.exceptions.ConnectionError:
    print("连接失败，请检查IP地址和端口")
except Exception as e:
    print(f"未知错误: {str(e)}")
