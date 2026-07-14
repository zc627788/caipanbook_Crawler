import requests
import uuid
import base64
import urllib.parse
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

pub_key_str = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA5GVku07yXCndaMS1evPIPyWwhbdWMVRqL4qg4OsKbzyTGmV4YkG8H0hwwrFLuPhqC5tL136aaizuL/lN5DRRbePct6syILOLLCBJ5J5rQyGr00l1zQvdNKYp4tT5EFlqw8tlPkibcsd5Ecc8sTYa77HxNeIa6DRuObC5H9t85ALJyDVZC3Y4ES/u61Q7LDnB3kG9MnXJsJiQxm1pLkE7Zfxy29d5JaXbbfwhCDSjE4+dUQoq2MVIt2qVjZSo5Hd/bAFGU1Lmc7GkFeLiLjNTOfECF52ms/dks92Wx/glfRuK4h/fcxtGB4Q2VXu5k68e/2uojs6jnFsMKVe+FVUDkQIDAQAB
-----END PUBLIC KEY-----"""

def encrypt_password(password):
    rsa_key = RSA.importKey(pub_key_str)
    cipher = PKCS1_v1_5.new(rsa_key)
    encrypted_bytes = cipher.encrypt(password.encode('utf-8'))
    encrypted_base64 = base64.b64encode(encrypted_bytes).decode('utf-8')
    return urllib.parse.quote(encrypted_base64, safe='')

username = "63-9568348610"
password = "Zc627788***"
encrypted_pwd = encrypt_password(password)

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
    
    # 2. Context App
    app_url = f"https://account.court.gov.cn/app?back_url={urllib.parse.quote(oauth_url, safe='')}"
    headers_app = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "referer": "https://wenshu.court.gov.cn/"
    }
    r_app = s.get(app_url, headers=headers_app, proxies=proxies, timeout=10)
    print("After App Cookies:", s.cookies.get_dict())
    
    # 3. Get Captcha
    r_cap = s.get("https://account.court.gov.cn/captcha/getBase64?appDomain=wenshu.court.gov.cn", proxies=proxies, timeout=10)
    cap_json = r_cap.json()
    token = cap_json["data"]["token"]
    session_id = cap_json["data"]["sessionId"]
    print("After GetCaptcha Cookies:", s.cookies.get_dict())
    
    # Save Image and solve manually in background if needed (but we want to see where ncCookie is set)
    # Since we can't solve it automatically here, we just want to look at the Set-Cookie headers in the response of each subsequent request.
