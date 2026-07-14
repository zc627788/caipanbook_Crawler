import requests

url_auth = "https://wenshu.court.gov.cn/tongyiLogin/authorize"
headers_auth = {
    "accept": "*/*",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "sec-ch-ua": "\"Google Chrome\";v=\"149\", \"Chromium\";v=\"149\", \"Not)A;Brand\";v=\"24\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "x-requested-with": "XMLHttpRequest",
    "referer": "https://wenshu.court.gov.cn/website/wenshu/181010CARHS5BS3C/index.html?open=login"
}

proxies = {
    'http': 'http://127.0.0.1:10808',
    'https': 'http://127.0.0.1:10808'
}

with requests.Session() as s:
    print("Initial Cookies:", s.cookies.get_dict())
    
    # 1. POST /tongyiLogin/authorize
    r1 = s.post(url_auth, headers=headers_auth, proxies=proxies, timeout=10)
    print("Step 1 Status:", r1.status_code)
    print("Step 1 Cookies:", s.cookies.get_dict())
    print("Step 1 Response Headers:", dict(r1.headers))
