import requests    
test_data = {
        "flag": 0, 
        "info": {
            '性别': "男",
            '年龄': 20,
            '身高': 175,
            '体重': 65.5,
            'activity_level': "b",
            '疾病情况': "糖尿病"
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
                   "食品名称":"凉拌土豆丝",
                    "食品克数": "100",
                    "食材信息": {
                        "土豆":"100"
                        }
                },
                {
                   "食品名称":"凉拌土豆丝",
                    "食品克数": "100",
                    "食材信息": {
                        "土豆":"100"
                        }
                },
                {
                   "食品名称":"凉拌土豆丝",
                    "食品克数": "100",
                    "食材信息": {
                        "土豆":"100"
                        }
                },
                {
                   "食品名称":"凉拌土豆丝",
                    "食品克数": "100",
                    "食材信息": {
                        "土豆":"100"
                        }
                },
                {
                   "食品名称":"凉拌土豆丝",
                    "食品克数": "100",
                    "食材信息": {
                        "土豆":"100"
                        }
                },
                {
                   "食品名称":"凉拌土豆丝",
                    "食品克数": "100",
                    "食材信息": {
                        "土豆":"100"
                        }
                },
                {
                   "食品名称":"凉拌土豆丝",
                    "食品克数": "100",
                    "食材信息": {
                        "土豆":"100"
                        }
                },
                {
                   "食品名称":"凉拌土豆丝",
                    "食品克数": "100",
                    "食材信息": {
                        "土豆":"100"
                        }
                },
                {
                   "食品名称":"凉拌土豆丝",
                    "食品克数": "100",
                    "食材信息": {
                        "土豆":"100"
                        }
                },
                {
                   "食品名称":"凉拌土豆丝",
                    "食品克数": "100",
                    "食材信息": {
                        "土豆":"100"
                        }
                }
            ]
            }
        }
ip_adress = 'http://192.168.99.55'
port = '8888'
url = f"{ip_adress}:{port}/getNutrition"
response = requests.post(url, json=test_data)
print("response",response.json())
