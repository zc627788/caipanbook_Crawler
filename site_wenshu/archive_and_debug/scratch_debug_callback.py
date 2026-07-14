"""
调试密码登录失败的核心原因：
authorizeCallBack 到底有没有触发服务端绑定用户到 SESSION？
通过精确复现浏览器请求链来找差异。
"""
import requests
import base64
import urllib.parse
import sys
import re
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

# ==================== 配置 ====================
USERNAME = "63-9568348610"
PASSWORD = "Zc627788***"
PUB_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA5GVku07yXCndaMS1evPIPyWwhbdWMVRqL4qg4OsKbzyTGmV4YkG8H0hwwrFLuPhqC5tL136aaizuL/lN5DRRbePct6syILOLLCBJ5J5rQyGr00l1zQvdNKYp4tT5EFlqw8tlPkibcsd5Ecc8sTYa77HxNeIa6DRuObC5H9t85ALJyDVZC3Y4ES/u61Q7LDnB3kG9MnXJsJiQxm1pLkE7Zfxy29d5JaXbbfwhCDSjE4+dUQoq2MVIt2qVjZSo5Hd/bAFGU1Lmc7GkFeLiLjNTOfECF52ms/dks92Wx/glfRuK4h/fcxtGB4Q2VXu5k68e/2uojs6jnFsMKVe+FVUDkQIDAQAB
-----END PUBLIC KEY-----"""
PROXIES = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}
CAPTCHA_FILE = r"D:\裁判文书逆向\site_wenshu\config\captcha.png"

def encrypt_pwd(pwd):
    key = RSA.importKey(PUB_KEY)
    cipher = PKCS1_v1_5.new(key)
    return urllib.parse.quote(base64.b64encode(cipher.encrypt(pwd.encode())).decode())

def check_login(session, referer):
    """检查登录态"""
    r = session.post(
        "https://wenshu.court.gov.cn/website/parse/rest.q4w",
        headers={
            "accept": "application/json, text/javascript, */*; q=0.01",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "referer": referer,
            "x-requested-with": "XMLHttpRequest",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        },
        data={"cfg": "com.lawyee.wbsttools.web.parse.dto.AppUserDTO@currentUser"},
        proxies=PROXIES, timeout=10
    )
    j = r.json()
    uid = j.get("result", {}).get("userId", "?") if isinstance(j.get("result"), dict) else "?"
    return uid, j

print("=" * 60)
print("  密码登录 authorizeCallBack 精细调试")
print("=" * 60)

session = requests.Session()
session.headers.update({
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
})

# Step 1: 获取 oauth_url
r1 = session.post(
    "https://wenshu.court.gov.cn/tongyiLogin/authorize",
    headers={"accept": "*/*", "x-requested-with": "XMLHttpRequest",
             "referer": "https://wenshu.court.gov.cn/website/wenshu/181010CARHS5BS3C/index.html?open=login"},
    proxies=PROXIES, timeout=10
)
oauth_url = r1.text.strip()
print(f"[1] wenshu SESSION after step1: {session.cookies.get('SESSION')}")
print(f"    oauth_url: {oauth_url[:80]}...")

# Step 2: 访问 account app 页面（建立 HOLDONKEY）
app_url = f"https://account.court.gov.cn/app?back_url={urllib.parse.quote(oauth_url, safe='')}"
session.get(app_url, headers={"accept": "text/html,*/*", "referer": "https://wenshu.court.gov.cn/"}, proxies=PROXIES, timeout=10)
holdonkey = session.cookies.get("HOLDONKEY", domain="account.court.gov.cn")
wenshu_session = session.cookies.get("SESSION", domain="wenshu.court.gov.cn")
print(f"[2] HOLDONKEY: {holdonkey[:20] if holdonkey else None}...")
print(f"    wenshu SESSION: {wenshu_session}")

# Step 3: 获取验证码
r3 = session.get("https://account.court.gov.cn/captcha/getBase64?appDomain=wenshu.court.gov.cn", proxies=PROXIES, timeout=10)
cap = r3.json()
token = cap["data"]["token"]
session_id = cap["data"]["sessionId"]

# 显示验证码
import base64 as b64mod
img_raw = cap["data"]["image"]
# 去掉 data:image/png;base64, 前缀
img_b64 = img_raw.split(",", 1)[-1] if "," in img_raw else img_raw
img_data = b64mod.b64decode(img_b64)
with open(CAPTCHA_FILE, "wb") as f:
    f.write(img_data)
print(f"\n🖼️ 验证码已保存，请输入验证码: ", end="", flush=True)
captcha = input()

# 校验验证码
rv = session.post(
    "https://account.court.gov.cn/captcha/verification",
    json={"sessionId": session_id, "verCode": captcha.upper(), "token": token},
    proxies=PROXIES, timeout=10
)
print(f"    验证码校验: {rv.json()}")

# Step 4: 提交登录
enc_pwd = encrypt_pwd(PASSWORD)
login_resp = session.post(
    "https://account.court.gov.cn/api/login",
    headers={
        "accept": "*/*", "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "x-requested-with": "XMLHttpRequest",
        "referer": app_url
    },
    data={"username": USERNAME, "password": enc_pwd, "bizToken": session_id, "imgVerifyToken": session_id, "appDomain": "wenshu.court.gov.cn"},
    proxies=PROXIES, timeout=10
)
login_json = login_resp.json()
print(f"\n[4] 登录结果: {login_json}")
new_holdonkey = session.cookies.get("HOLDONKEY", domain="account.court.gov.cn")
print(f"    新 HOLDONKEY: {new_holdonkey[:20] if new_holdonkey else None}...")
wenshu_session_after_login = session.cookies.get("SESSION", domain="wenshu.court.gov.cn")
print(f"    wenshu SESSION (after login): {wenshu_session_after_login}")

if not (login_json.get("success") or str(login_json.get("code")) == "000000"):
    print("❌ 登录失败！"); sys.exit(1)

# Step 5: 直接检查 authorizeCallBack 的响应（关键步骤）
# 5a: 先检查当前 wenshu 登录状态
print("\n[5a] 登录后立即检查 wenshu 登录态（还没 OAuth 跳转）:")
uid, j = check_login(session, "https://wenshu.court.gov.cn/website/wenshu/181010CARHS5BS3C/index.html")
print(f"     userId = {uid}")

# 5b: 访问 oauth/authorize (account 侧)，获取 code
print(f"\n[5b] 访问 oauth_url: {oauth_url[:80]}...")
r5b = session.get(oauth_url, headers={
    "accept": "text/html,*/*", "upgrade-insecure-requests": "1",
    "referer": app_url
}, proxies=PROXIES, allow_redirects=False, timeout=15)
print(f"     Status: {r5b.status_code}")
print(f"     Location: {r5b.headers.get('Location', '(none)')}")
print(f"     Set-Cookie: {r5b.headers.get('Set-Cookie', '(none)')}")
print(f"     All cookies now: {[(c.domain, c.name, c.value[:20]) for c in session.cookies]}")

callback_url = r5b.headers.get("Location")
if not callback_url:
    print("❌ 未获取到回调 URL"); sys.exit(1)

# 5c: 访问 authorizeCallBack，触发服务端 Session 绑定
print(f"\n[5c] 访问 callback_url: {callback_url[:100]}...")
r5c = session.get(callback_url, headers={
    "accept": "text/html,*/*", "upgrade-insecure-requests": "1",
    "referer": oauth_url
}, proxies=PROXIES, allow_redirects=False, timeout=15)
print(f"     Status: {r5c.status_code}")
print(f"     Set-Cookie: {r5c.headers.get('Set-Cookie', '(none)')}")
print(f"     Content: {r5c.text[:500]}")
print(f"     All cookies now: {[(c.domain, c.name, c.value[:20]) for c in session.cookies]}")

# 5d: 立即检查 wenshu 登录状态
print("\n[5d] 访问 callback 后立即检查 wenshu 登录态:")
uid, j = check_login(session, "https://wenshu.court.gov.cn/website/wenshu/181010CARHS5BS3C/index.html")
print(f"     userId = {uid}")

# 5e: 访问 window.open 的 landing url
landing_match = re.search(r"window\.open\s*\(\s*'([^']+)'", r5c.text)
if landing_match:
    landing_path = landing_match.group(1)
    landing_url = "https://wenshu.court.gov.cn" + landing_path if landing_path.startswith("/") else landing_path
    print(f"\n[5e] 访问 landing URL: {landing_url}")
    r5e = session.get(landing_url, headers={
        "accept": "text/html,*/*", "upgrade-insecure-requests": "1",
        "referer": callback_url
    }, proxies=PROXIES, timeout=15)
    print(f"     Status: {r5e.status_code}")
    print(f"     Set-Cookie: {r5e.headers.get('Set-Cookie', '(none)')}")
    
    # 5f: 最终检查
    print("\n[5f] 访问 landing 后最终检查 wenshu 登录态:")
    uid, j = check_login(session, landing_url)
    print(f"     userId = {uid}")
    if "anonymous" not in str(uid).lower():
        print(f"     🎉 登录验证通过!")
    else:
        print(f"     ❌ 仍然是匿名！")
        print(f"     完整响应: {j}")
