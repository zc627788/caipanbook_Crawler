import requests

endpoints = [
    "get", "getImg", "getCode", "image", "img", "generate", "create", "captcha", "get_captcha", "getVerifyCode"
]

for ep in endpoints:
    url = f"https://account.court.gov.cn/captcha/{ep}"
    # Test GET
    r_get = requests.get(url, params={"appkey": "akan"})
    # Test POST
    r_post = requests.post(url, data={"appkey": "akan"})
    
    print(f"GET  /captcha/{ep} -> {r_get.status_code}")
    print(f"POST /captcha/{ep} -> {r_post.status_code}")
