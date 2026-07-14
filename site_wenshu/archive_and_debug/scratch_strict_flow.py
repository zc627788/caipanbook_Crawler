"""
严格还原浏览器完整流程：
1. wenshu tongyiLogin/authorize → 获取 oauth_url
2. getBase64 → 获取验证码图片+sessionId
3. captcha/validate → 验证验证码（获取 cert），referrer = app?back_url=...
4. api/login → 登录（referrer = app?back_url=...），bizToken=imgVerifyToken=sessionId
5. oauth/authorize → 303 → CallBackController
6. 验证 currentUser

核心假设：validate 必须在 login 之前完成，且 referrer 必须是完整的 app?back_url=... URL
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

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"

def encrypt_pwd(pwd):
    key = RSA.importKey(PUB_KEY)
    return urllib.parse.quote(base64.b64encode(PKCS1_v1_5.new(key).encrypt(pwd.encode())).decode())

session = requests.Session()
session.headers.update({"user-agent": UA})

# ==================================================================
# Step 1: wenshu → oauth_url
# ==================================================================
print("=" * 60)
print("[1] 获取 OAuth URL...")
r1 = session.post("https://wenshu.court.gov.cn/tongyiLogin/authorize",
    headers={
        "accept": "*/*",
        "x-requested-with": "XMLHttpRequest",
        "referer": "https://wenshu.court.gov.cn/website/wenshu/181010CARHS5BS3C/index.html?open=login"
    },
    proxies=PROXIES, timeout=10)
oauth_url = r1.text.strip()
print(f"  oauth_url: {oauth_url[:80]}...")
print(f"  wenshu SESSION = {session.cookies.get('SESSION', '无')}")

# ==================================================================
# Step 2: 访问 account app页面（带完整 back_url）
# ==================================================================
back_url = urllib.parse.quote(oauth_url, safe='')
app_url_full = f"https://account.court.gov.cn/app?back_url={back_url}"
print(f"\n[2] 访问 account app 页面...")
session.get(app_url_full, headers={"referer": "https://wenshu.court.gov.cn/"}, proxies=PROXIES, timeout=10)
print(f"  account SESSION = {session.cookies.get('HOLDONKEY', domain='account.court.gov.cn', default='无')[:16]}...")

# ==================================================================
# Step 3: getBase64 验证码（referrer = "https://account.court.gov.cn/app"）
# ==================================================================
print(f"\n[3] 获取验证码（referrer=app）...")
r3 = session.get("https://account.court.gov.cn/captcha/getBase64?appDomain=wenshu.court.gov.cn",
    headers={
        "accept": "*/*",
        "x-requested-with": "XMLHttpRequest",
        "referer": "https://account.court.gov.cn/app"   # ← 注意这里是 /app 不带 back_url
    },
    proxies=PROXIES, timeout=10)
cap = r3.json()
token = cap["data"]["token"]
session_id = cap["data"]["sessionId"]
img_raw = cap["data"]["image"]
img_b64 = img_raw.split(",", 1)[-1] if "," in img_raw else img_raw
with open(CAPTCHA_FILE, "wb") as f:
    f.write(base64.b64decode(img_b64))
print(f"  sessionId = {session_id}")
print(f"🖼️  验证码已保存，请输入: ", end="", flush=True)
captcha_answer = input().strip().upper()

# ==================================================================
# Step 4: captcha/validate（referrer 带完整 back_url）
# ==================================================================
print(f"\n[4] 验证验证码（referrer=app?back_url=...）...")
validate_referrer = app_url_full  # ← 浏览器里 referrer 是完整 app?back_url
r4 = session.post("https://account.court.gov.cn/captcha/validate",
    headers={
        "accept": "*/*",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "x-requested-with": "XMLHttpRequest",
        "referer": validate_referrer
    },
    data={
        "appkey": "akan",
        "answer": captcha_answer,
        "token": token,
        "sessionId": session_id,
        "appDomain": "wenshu.court.gov.cn"
    },
    proxies=PROXIES, timeout=10)
val_json = r4.json()
print(f"  validate 响应: {json.dumps(val_json, ensure_ascii=False)}")
cert = val_json.get("data", {}).get("cert", None)
print(f"  cert: {cert[:20] if cert else '无'}...")

if val_json.get("code") != 0:
    print("❌ 验证码校验失败，退出")
    sys.exit(1)
print("  ✅ 验证码校验成功！")

# ==================================================================
# Step 5: api/login（referrer 带完整 back_url）
# ==================================================================
print(f"\n[5] 登录（referrer=app?back_url=...）...")
enc_pwd = encrypt_pwd(PASSWORD)
r5 = session.post("https://account.court.gov.cn/api/login",
    headers={
        "accept": "*/*",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "x-requested-with": "XMLHttpRequest",
        "referer": validate_referrer   # ← 同样的 referrer
    },
    data={
        "username": USERNAME,
        "password": enc_pwd,
        "bizToken": session_id,
        "imgVerifyToken": session_id,
        "appDomain": "wenshu.court.gov.cn"
    },
    proxies=PROXIES, timeout=10)
login_json = r5.json()
print(f"  登录响应: {login_json}")
if not (login_json.get("success") or str(login_json.get("code")) == "000000"):
    print("❌ 登录失败"); sys.exit(1)
print("  ✅ 登录成功！")
print("  Cookies after login:")
for c in session.cookies:
    print(f"    {c.domain} | {c.name}={c.value[:20]}...")

# ==================================================================
# Step 6: oauth/authorize → 303 → CallBack
# ==================================================================
print(f"\n[6] OAuth 授权回调...")
r6 = session.get(oauth_url,
    headers={"accept": "text/html,*/*", "referer": app_url_full},
    proxies=PROXIES, allow_redirects=False, timeout=15)
callback_url = r6.headers.get("Location")
print(f"  oauth → {r6.status_code}, Location: {callback_url[:80] if callback_url else '无'}...")

r6b = session.get(callback_url,
    headers={"accept": "text/html,*/*", "referer": oauth_url},
    proxies=PROXIES, allow_redirects=False, timeout=15)
print(f"  callback → {r6b.status_code}")
print(f"  Set-Cookie: {r6b.headers.get('Set-Cookie', '无')}")
print(f"  Body: {r6b.text[:200]}")

# 落地页
landing_match = re.search(r"window\.open\s*\(\s*'([^']+)'", r6b.text)
landing_url = "https://wenshu.court.gov.cn/"
if landing_match:
    path = landing_match.group(1)
    landing_url = "https://wenshu.court.gov.cn" + path if path.startswith("/") else path
    session.get(landing_url, headers={"referer": callback_url}, proxies=PROXIES, timeout=15)

# ==================================================================
# Step 7: 验证 currentUser
# ==================================================================
print(f"\n[7] 验证登录态...")
chk = session.post("https://wenshu.court.gov.cn/website/parse/rest.q4w",
    headers={
        "accept": "application/json, text/javascript, */*; q=0.01",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "x-requested-with": "XMLHttpRequest",
        "referer": landing_url
    },
    data={"cfg": "com.lawyee.wbsttools.web.parse.dto.AppUserDTO@currentUser"},
    proxies=PROXIES, timeout=10)
chk_json = chk.json()
print(json.dumps(chk_json, ensure_ascii=False, indent=2))
result = chk_json.get("result", {})
if isinstance(result, dict):
    uid = result.get("userName") or result.get("userId", "?")
    print(f"\n{'🎉 登录成功！userName = ' + uid if 'anonymous' not in str(uid).lower() else '❌ 仍然匿名'}")
