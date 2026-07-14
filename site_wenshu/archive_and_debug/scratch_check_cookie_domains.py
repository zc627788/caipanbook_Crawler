import requests
import urllib.parse

url_auth = "https://wenshu.court.gov.cn/tongyiLogin/authorize"
headers_auth = {
    "accept": "*/*",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "x-requested-with": "XMLHttpRequest",
    "referer": "https://wenshu.court.gov.cn/website/wenshu/181010CARHS5BS3C/index.html?open=login"
}

proxies = {
    'http': 'http://127.0.0.1:10808',
    'https': 'http://127.0.0.1:10808'
}

def print_cookies(session, label):
    print(f"\n--- Cookies at {label} ---")
    for cookie in session.cookies:
        print(f"Domain: {cookie.domain} | Name: {cookie.name} | Value: {cookie.value}")

with requests.Session() as s:
    # 1. OAuth Init
    r_init = s.post(url_auth, headers=headers_auth, proxies=proxies, timeout=10)
    oauth_url = r_init.text.strip()
    print_cookies(s, "1. Post to authorize")
    
    # 2. Context App
    app_url = f"https://account.court.gov.cn/app?back_url={urllib.parse.quote(oauth_url, safe='')}"
    headers_app = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "referer": "https://wenshu.court.gov.cn/"
    }
    r_app = s.get(app_url, headers=headers_app, proxies=proxies, timeout=10)
    print_cookies(s, "2. Get app login page")
