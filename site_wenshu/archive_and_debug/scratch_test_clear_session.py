"""
测试发现，只有在 authorizeCallBack 步骤时【不带 wenshu SESSION】，
让服务器重新种一个新的 SESSION，才能绑定成功。
这里我们要验证这个理论：在访问 authorizeCallBack 时，清空 Cookie。
"""
import requests, base64, urllib.parse, sys, re, time
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

USERNAME = "63-9568348610"
PASSWORD = "Zc627788***"
PUB_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA5GVku07yXCndaMS1evPIPyWwhbdWMVRqL4qg4OsKbzyTGmV4YkG8H0hwwrFLuPhqC5tL136aaizuL/lN5DRRbePct6syILOLLCBJ5J5rQyGr00l1zQvdNKYp4tT5EFlqw8tlPkibcsd5Ecc8sTYa77HxNeIa6DRuObC5H9t85ALJyDVZC3Y4ES/u61Q7LDnB3kG9MnXJsJiQxm1pLkE7Zfxy29d5JaXbbfwhCDSjE4+dUQoq2MVIt2qVjZSo5Hd/bAFGU1Lmc7GkFeLiLjNTOfECF52ms/dks92Wx/glfRuK4h/fcxtGB4Q2VXu5k68e/2uojs6jnFsMKVe+FVUDkQIDAQAB
-----END PUBLIC KEY-----"""
PROXIES = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}

def encrypt_pwd(pwd):
    key = RSA.importKey(PUB_KEY)
    return urllib.parse.quote(base64.b64encode(PKCS1_v1_5.new(key).encrypt(pwd.encode())).decode())

def check_login(session, referer):
    r = session.post(
        "https://wenshu.court.gov.cn/website/parse/rest.q4w",
        headers={"accept": "application/json, text/javascript, */*; q=0.01",
                 "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                 "referer": referer, "x-requested-with": "XMLHttpRequest",
                 "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        data={"cfg": "com.lawyee.wbsttools.web.parse.dto.AppUserDTO@currentUser"},
        proxies=PROXIES, timeout=10
    )
    return r.json()

session = requests.Session()
session.headers.update({"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

# Step 1: OAuth init
r1 = session.post("https://wenshu.court.gov.cn/tongyiLogin/authorize",
    headers={"accept": "*/*", "x-requested-with": "XMLHttpRequest",
             "referer": "https://wenshu.court.gov.cn/website/wenshu/181010CARHS5BS3C/index.html?open=login"},
    proxies=PROXIES, timeout=10)
oauth_url = r1.text.strip()
print(f"Step 1: SESSION = {session.cookies.get('SESSION')}")

# Step 2: App context
app_url = f"https://account.court.gov.cn/app?back_url={urllib.parse.quote(oauth_url, safe='')}"
session.get(app_url, headers={"referer": "https://wenshu.court.gov.cn/"}, proxies=PROXIES, timeout=10)

# Step 3: 验证码
r3 = session.get("https://account.court.gov.cn/captcha/getBase64?appDomain=wenshu.court.gov.cn", proxies=PROXIES, timeout=10)
cap = r3.json()
token = cap["data"]["token"]
session_id = cap["data"]["sessionId"]

img_raw = cap["data"]["image"]
img_b64 = img_raw.split(",", 1)[-1] if "," in img_raw else img_raw
with open(r"D:\裁判文书逆向\site_wenshu\config\captcha.png", "wb") as f:
    f.write(base64.b64decode(img_b64))
captcha = input("\n🖼️ 输入验证码: ").strip().upper()

# Step 4: 登录
enc_pwd = encrypt_pwd(PASSWORD)
login_resp = session.post("https://account.court.gov.cn/api/login",
    headers={"accept": "*/*", "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
             "x-requested-with": "XMLHttpRequest", "referer": app_url},
    data={"username": USERNAME, "password": enc_pwd,
          "bizToken": session_id, "imgVerifyToken": session_id, "appDomain": "wenshu.court.gov.cn"},
    proxies=PROXIES, timeout=10)
print(f"\n[4] 登录: {login_resp.json()}")

# Step 5: OAuth 授权
r5b = session.get(oauth_url, headers={"accept": "text/html,*/*", "referer": app_url},
    proxies=PROXIES, allow_redirects=False, timeout=15)
callback_url = r5b.headers.get("Location")
print(f"\n[5] callback_url: {callback_url[:90]}")

# 🚀 核心测试点：清空 wenshu 的 SESSION，让 authorizeCallBack 强制种一个新的！
del session.cookies["SESSION"]
print(f"清空 SESSION 后: {session.cookies.get('SESSION')}")

r5c = session.get(callback_url, headers={"accept": "text/html,*/*", "referer": oauth_url},
    proxies=PROXIES, allow_redirects=False, timeout=15)
print(f"\n[5c] authorizeCallBack → {r5c.status_code}")
print(f"     Set-Cookie: {r5c.headers.get('Set-Cookie', '无')}")

landing_url = "https://wenshu.court.gov.cn/website/wenshu/181029CR4M5A62CH/index.html?"
session.get(landing_url, headers={"accept": "text/html,*/*", "referer": callback_url}, proxies=PROXIES, timeout=15)

print("\n📋 验证:")
chk_json = check_login(session, landing_url)
print(chk_json)
