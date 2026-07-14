import requests

url = "https://account.court.gov.cn/captcha/getBase64?appDomain=wenshu.court.gov.cn"
headers = {
    "accept": "*/*",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    "x-requested-with": "XMLHttpRequest"
}
proxies = {
    'http': 'http://127.0.0.1:10808',
    'https': 'http://127.0.0.1:10808'
}

resp = requests.get(url, headers=headers, proxies=proxies, timeout=10)
data = resp.json()
print("Success:", data.get("code") == 0)
print("Keys in data['data']:", data.get("data", {}).keys())
print("Token:", data.get("data", {}).get("token")[:30] + "...")
print("SessionId:", data.get("data", {}).get("sessionId"))
