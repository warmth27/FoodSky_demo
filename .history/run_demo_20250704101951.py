import requests    
test_data = {
        "flag": 0, 
        "info": {
            '性别': "男",
            '年龄': 20,
            '身高': 175,
            '体重': 65.5,
            'activity_level': None,
            '疾病情况': None
        },
        "data": {
            "餐别":"午餐",
            }
        }
ip_adress = 'http://192.168.99.55'
port = '8888'
url = f"{ip_adress}:{port}/getNutrition"
response = requests.post(url, json=test_data)
print("response",response.json())
