import requests

# Let's test what the validate endpoint actually returns when successful
url = "https://account.court.gov.cn/captcha/getBase64?appDomain=wenshu.court.gov.cn"
headers = {
    "accept": "*/*",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "x-requested-with": "XMLHttpRequest"
}
proxies = {
    'http': 'http://127.0.0.1:10808',
    'https': 'http://127.0.0.1:10808'
}

resp = requests.get(url, headers=headers, proxies=proxies, timeout=10)
cap_data = resp.json()
token = cap_data["data"]["token"]
session_id = cap_data["data"]["sessionId"]

print(f"Token: {token[:20]}...")
print(f"Session ID: {session_id}")

# Now prompt for user answer
import os
import base64
img_b64 = cap_data["data"]["image"].split(",")[1]
with open("temp_cap.png", "wb") as f:
    f.write(base64.b64decode(img_b64))

print("Image saved to temp_cap.png")
ans = input("Enter captcha: ").strip()

validate_url = "https://account.court.gov.cn/captcha/validate"
validate_headers = {
    "accept": "*/*",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "x-requested-with": "XMLHttpRequest",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
validate_body = {
    "appkey": "akan",
    "answer": ans.upper(),
    "token": token,
    "sessionId": session_id,
    "appDomain": "wenshu.court.gov.cn"
}

resp_val = requests.post(validate_url, headers=validate_headers, data=validate_body, proxies=proxies, timeout=10)
print("Validate Status:", resp_val.status_code)
print("Validate Response:", resp_val.text)
