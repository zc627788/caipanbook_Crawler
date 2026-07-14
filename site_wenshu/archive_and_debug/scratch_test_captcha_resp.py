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
print(resp.status_code)
print(resp.text[:1000])
