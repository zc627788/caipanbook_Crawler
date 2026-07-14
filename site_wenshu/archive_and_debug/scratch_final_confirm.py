"""
最终确认：密码登录完整流程 + 正确读取 userId
"""
import requests, base64, urllib.parse, sys, re, time, json
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

USERNAME = "63-9568348610"
PASSWORD = "Zc627788***"
PUB_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA5GVku07yXCndaMS1evPIPyWwhbdWMVRqL4qg4OsKbzyTGmV4YkG8H0hwwrFLuPhqC5tL136aaizuL/lN5DRRbePct6syILOLLCBJ5J5rQyGr00l1zQvdNKYp4tT5EFlqw8tlPkibcsd5Ecc8sTYa77HxNeIa6DRuObC5H9t85ALJyDVZC3Y4ES/u61Q7LDnB3kG9MnXJsJiQxm1pLkE7Zfxy29d5JaXbbfwhCDSjE4+dUQoq2MVIt2qVjZSo5Hd/bAFGU1Lmc7GkFeLiLjNTOfECF52ms/dks92Wx/glfRuK4h/fcxtGB4Q2VXu5k68e/2uojs6jnFsMKVe+FVUDkQIDAQAB
-----END PUBLIC KEY-----"""
PROXIES = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}
CAPTCHA_FILE = r"D:\裁判文书逆向\site_wenshu\config\captcha.png"
SESSION_FILE = r"D:\裁判文书逆向\site_wenshu\config\session.json"

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

# Step 2: App context
app_url = f"https://account.court.gov.cn/app?back_url={urllib.parse.quote(oauth_url, safe='')}"
session.get(app_url, headers={"referer": "https://wenshu.court.gov.cn/"}, proxies=PROXIES, timeout=10)

# Step 3: 获取验证码
r3 = session.get("https://account.court.gov.cn/captcha/getBase64?appDomain=wenshu.court.gov.cn", proxies=PROXIES, timeout=10)
cap = r3.json()
token = cap["data"]["token"]
session_id = cap["data"]["sessionId"]

img_raw = cap["data"]["image"]
img_b64 = img_raw.split(",", 1)[-1] if "," in img_raw else img_raw
with open(CAPTCHA_FILE, "wb") as f:
    f.write(base64.b64decode(img_b64))
print(f"\n🖼️ 验证码已保存，请输入: ", end="", flush=True)
captcha = input().strip().upper()

# Step 4: 登录（忽略验证码校验，直接传入 sessionId）
enc_pwd = encrypt_pwd(PASSWORD)
login_resp = session.post("https://account.court.gov.cn/api/login",
    headers={"accept": "*/*", "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
             "x-requested-with": "XMLHttpRequest", "referer": app_url},
    data={"username": USERNAME, "password": enc_pwd,
          "bizToken": session_id, "imgVerifyToken": session_id, "appDomain": "wenshu.court.gov.cn"},
    proxies=PROXIES, timeout=10)
login_json = login_resp.json()
print(f"[4] 登录: {login_json}")
if not (login_json.get("success") or str(login_json.get("code")) == "000000"):
    print("❌ 登录失败"); sys.exit(1)

# Step 5: OAuth callback
r5b = session.get(oauth_url, headers={"accept": "text/html,*/*", "referer": app_url},
    proxies=PROXIES, allow_redirects=False, timeout=15)
callback_url = r5b.headers.get("Location")
if not callback_url:
    sys.exit("❌ 无 Location")

r5c = session.get(callback_url, headers={"accept": "text/html,*/*", "referer": oauth_url},
    proxies=PROXIES, allow_redirects=False, timeout=15)
print(f"[5c] authorizeCallBack → {r5c.status_code}")

# Step 6: 访问 landing page
landing_match = re.search(r"window\.open\s*\(\s*'([^']+)'", r5c.text)
landing_url = "https://wenshu.court.gov.cn/"
if landing_match:
    path = landing_match.group(1)
    landing_url = "https://wenshu.court.gov.cn" + path if path.startswith("/") else path
    session.get(landing_url, headers={"accept": "text/html,*/*", "referer": r5c.url},
        proxies=PROXIES, timeout=15)

# Step 7: 最终检查 - 打印完整响应
print("\n📋 最终 currentUser 完整响应:")
chk_json = check_login(session, landing_url)
print(json.dumps(chk_json, ensure_ascii=False, indent=2))

result = chk_json.get("result", {})
if isinstance(result, dict):
    uid = result.get("userId", "?")
    name = result.get("realName", "?")
    mobile = result.get("mobile", "?")
    role = result.get("role", "?")
    print(f"\n{'🎉 登录验证通过!' if 'anonymous' not in str(uid).lower() else '❌ 仍匿名'}")
    print(f"  userId: {uid}, realName: {name}, mobile: {mobile}, role: {role}")
    
    if "anonymous" not in str(uid).lower():
        # 保存 session
        final_cookies = {c.name: c.value for c in session.cookies if "wenshu" in c.domain}
        session_data = {"cookies": final_cookies, "timestamp": int(time.time()),
                        "userId": uid, "realName": name}
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Session 已保存至: {SESSION_FILE}")
        print(f"📋 Cookie: {final_cookies}")
