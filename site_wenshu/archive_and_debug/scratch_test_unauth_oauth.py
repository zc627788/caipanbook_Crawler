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

with requests.Session() as s:
    # 1. OAuth Init
    r_init = s.post(url_auth, headers=headers_auth, proxies=proxies, timeout=10)
    oauth_url = r_init.text.strip()
    print("OAuth URL:", oauth_url)
    
    # 2. Directly visit oauth_url without logging in (no HOLDONKEY)
    headers_visit = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "referer": "https://wenshu.court.gov.cn/"
    }
    resp = s.get(oauth_url, headers=headers_visit, proxies=proxies, allow_redirects=False, timeout=15)
    print("Response Status:", resp.status_code)
    print("Location Header:", resp.headers.get("Location"))
