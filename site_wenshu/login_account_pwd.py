#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
裁判文书网 - 账号密码登录纯协议全自动对接工具
采用纯 HTTP 协议抓包拆解，直接绕过验证码
包含：OAuth 2.0 授权跳转 -> 密码加密登录 -> 自动换取文书网 Cookie -> 持久化会话
"""

import json
import os
import sys
import time
import base64
import urllib.parse
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

# ⚡ 使用 curl_cffi 替代 requests，伪装 Chrome TLS 指纹绕过 WAF JA3 检测
from curl_cffi import requests
# 全局 TLS 指纹伪装版本
TLS_IMPERSONATE = "chrome120"


def _cookie_attr(cookie_jar, cookie_or_name, attr):
    """
    兼容 curl_cffi（cookie 是 str）和 requests（cookie 是对象）。
    attr: 'domain' | 'name' | 'value'
    """
    if isinstance(cookie_or_name, str):
        # curl_cffi: cookie 是字符串 name，从 jar 中取值
        if attr == "name":
            return cookie_or_name
        if attr == "value":
            return cookie_jar.get(cookie_or_name, "")
        if attr == "domain":
            return "?"
    else:
        # requests: cookie 是对象
        return getattr(cookie_or_name, attr, "?")


def _cookie_dump(cookie_jar):
    """打印 cookie jar 中的所有 cookie（兼容两种库）"""
    for c in cookie_jar:
        name = _cookie_attr(cookie_jar, c, "name")
        value = _cookie_attr(cookie_jar, c, "value")
        domain = _cookie_attr(cookie_jar, c, "domain")
        if len(str(value)) > 40:
            value = str(value)[:40] + "..."
        print(f"  Domain={domain} | {name}={value}")


def _chrome_session():
    """
    创建一个自动附带 Chrome TLS 指纹伪装的 Session。
    所有 .get() / .post() 自动注入 impersonate=TLS_IMPERSONATE。
    """
    sess = requests.Session()

    _orig_get = sess.get
    _orig_post = sess.post

    def _get(url, **kwargs):
        kwargs.setdefault("impersonate", TLS_IMPERSONATE)
        return _orig_get(url, **kwargs)

    def _post(url, **kwargs):
        kwargs.setdefault("impersonate", TLS_IMPERSONATE)
        return _orig_post(url, **kwargs)

    sess.get = _get
    sess.post = _post
    return sess

# ==============================================================================
# 配置区域
# ==============================================================================
# 真实明文账号密码
USERNAME = "63-9568348610"
# 真实明文密码
PASSWORD = "Zc627788***"

PROXIES = {
    'http': 'http://127.0.0.1:10808',
    'https': 'http://127.0.0.1:10808'
}

CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'config')
os.makedirs(CONFIG_DIR, exist_ok=True)
SESSION_FILE = os.path.join(CONFIG_DIR, 'session.json')

# 提取到的前端 RSA 公钥
RSA_PUB_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA5GVku07yXCndaMS1evPIPyWwhbdWMVRqL4qg4OsKbzyTGmV4YkG8H0hwwrFLuPhqC5tL136aaizuL/lN5DRRbePct6syILOLLCBJ5J5rQyGr00l1zQvdNKYp4tT5EFlqw8tlPkibcsd5Ecc8sTYa77HxNeIa6DRuObC5H9t85ALJyDVZC3Y4ES/u61Q7LDnB3kG9MnXJsJiQxm1pLkE7Zfxy29d5JaXbbfwhCDSjE4+dUQoq2MVIt2qVjZSo5Hd/bAFGU1Lmc7GkFeLiLjNTOfECF52ms/dks92Wx/glfRuK4h/fcxtGB4Q2VXu5k68e/2uojs6jnFsMKVe+FVUDkQIDAQAB
-----END PUBLIC KEY-----"""


def encrypt_password(password):
    """
    使用提取的 RSA 公钥加密明文密码
    """
    rsa_key = RSA.importKey(RSA_PUB_KEY)
    cipher = PKCS1_v1_5.new(rsa_key)
    encrypted_bytes = cipher.encrypt(password.encode('utf-8'))
    encrypted_base64 = base64.b64encode(encrypted_bytes).decode('utf-8')
    return urllib.parse.quote(encrypted_base64)


def init_oauth(session):
    """
    第一步：调用文书网统一登录接口，获取 OAuth 授权跳转链接
    并在 account.court.gov.cn 创建登录上下文
    """
    url = "https://wenshu.court.gov.cn/tongyiLogin/authorize"
    headers = {
        "accept": "*/*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "sec-ch-ua": "\"Google Chrome\";v=\"149\", \"Chromium\";v=\"149\", \"Not)A;Brand\";v=\"24\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "x-requested-with": "XMLHttpRequest",
        "referer": "https://wenshu.court.gov.cn/website/wenshu/181010CARHS5BS3C/index.html?open=login"
    }
    print("⏳ [1/4] 正在初始化文书网 OAuth 鉴权链路...")
    try:
        resp = session.post(url, headers=headers, proxies=PROXIES, timeout=10)
        oauth_url = resp.text.strip()
        if not oauth_url.startswith("http"):
            print("❌ 获取 OAuth 跳转地址异常:", oauth_url)
            sys.exit(1)
        print("✅ 成功获取 OAuth 授权跳转地址！")
    except Exception as e:
        print(f"❌ 初始化请求失败（请检查网络或 10808 代理）: {e}")
        sys.exit(1)
    
    print("⏳ [2/4] 正在访问 account 登录上下文页面（模仿浏览器行为）...")
    app_url = f"https://account.court.gov.cn/app?back_url={urllib.parse.quote(oauth_url, safe='')}"
    login_page_headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "referer": "https://wenshu.court.gov.cn/"
    }
    # ⚠️ 关键：account 页面可能通过 302 跳转回 wenshu，这会覆盖 tongyiLogin 产生的 SESSION
    # 策略：先 allow_redirects=False 拿到 HOLDONKEY + ncCookie（从 Set-Cookie 头），
    # 同时打印响应状态码判断是否发生了跳转；如果跳转了，SESSION 可能已被覆盖
    login_resp = session.get(app_url, headers=login_page_headers, proxies=PROXIES,
                             allow_redirects=False, timeout=15)
    print(f"  [Debug] account 页面 HTTP {login_resp.status_code}")
    if "Location" in login_resp.headers:
        print(f"  [Debug] ⚠️ 服务端返回了 302 跳转: {login_resp.headers['Location'][:100]}...")

    holdonkey = session.cookies.get('HOLDONKEY', domain='account.court.gov.cn')
    nccookie = session.cookies.get('ncCookie', domain='account.court.gov.cn')
    if holdonkey:
        print(f"✅ account 登录上下文已初始化！HOLDONKEY: {holdonkey[:16]}...")
    else:
        print("⚠️ 未获取到 HOLDONKEY，account 登录上下文初始化可能失败")
    if nccookie:
        print(f"✅ 获取到反爬安全 cookie ncCookie: {nccookie[:20]}...")
    else:
        print("⚠️ 未获取到 ncCookie（反爬安全 cookie），后续请求可能被 WAF 拦截")
        print("   尝试通过访问 account 首页来触发 ncCookie 下发...")
        # 追加一次 account 首页访问，可能触发安全 cookie 下发
        r_nc = session.get("https://account.court.gov.cn/app", headers={
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "referer": "https://wenshu.court.gov.cn/"
        }, proxies=PROXIES, allow_redirects=False, timeout=10)
        nccookie = session.cookies.get('ncCookie', domain='account.court.gov.cn')
        if nccookie:
            print(f"  ✅ 二次请求后获取到 ncCookie: {nccookie[:20]}...")
        else:
            print("  ⚠️ 仍未获取到 ncCookie，后续 /api/login 可能被拦截")
    
    return oauth_url, app_url


def login_with_password(session, oauth_url, app_url):
    """
    第三步：处理验证码，加密密码，并提交登录请求，随后完成回调
    """
    captcha_png_path = os.path.join(CONFIG_DIR, 'captcha.png')
    
    # 验证码循环
    session_id = None
    while True:
        print("\n⏳ 正在获取验证码图片...")
        captcha_get_url = "https://account.court.gov.cn/captcha/getBase64?appDomain=wenshu.court.gov.cn"
        headers_get = {
            "accept": "*/*",
            "referer": app_url,
            "x-requested-with": "XMLHttpRequest",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
        }
        
        try:
            resp_cap = session.get(captcha_get_url, headers=headers_get, proxies=PROXIES, timeout=10)
            cap_data = resp_cap.json()
        except Exception as e:
            print(f"❌ 获取验证码失败: {e}")
            sys.exit(1)
            
        if cap_data.get("code") == 0:
            img_b64 = cap_data["data"]["image"]
            token = cap_data["data"]["token"]
            session_id = cap_data["data"]["sessionId"]
            
            # 去掉 data:image/jpg;base64, 前缀并保存图片
            if "," in img_b64:
                img_b64 = img_b64.split(",")[1]
            img_data = base64.b64decode(img_b64)
            with open(captcha_png_path, "wb") as f:
                f.write(img_data)
                
            print(f"🖼️ 验证码已保存至: {captcha_png_path}")
            answer = input("💡 请查看验证码图片并在此输入验证码: ").strip()
            
            # ⚠️ 关键：referrer 必须是完整的 app?back_url=... URL
            # 服务端通过 referrer 关联当前 OAuth 会话，不带 back_url 会导致 session 绑定失败
            print("⏳ 正在校验验证码...")
            validate_url = "https://account.court.gov.cn/captcha/validate"
            validate_headers = {
                "accept": "*/*",
                "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                "referer": app_url,   # app_url 已经是 app?back_url=完整OAuth URL
                "x-requested-with": "XMLHttpRequest",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            validate_body = {
                "appkey": "akan",
                "answer": answer,
                "token": token,
                "sessionId": session_id,
                "appDomain": "wenshu.court.gov.cn"
            }
            
            try:
                resp_val = session.post(validate_url, headers=validate_headers, data=validate_body, proxies=PROXIES, timeout=10)
                val_json = resp_val.json()
            except Exception as e:
                print(f"❌ 校验验证码时发生网络异常: {e}")
                sys.exit(1)
                
            if val_json.get("code") == 0 or val_json.get("success"):
                cert = val_json.get("data", {}).get("cert", "")
                print(f"✅ 验证码校验成功！cert={cert[:20]}...")
                break
            else:
                print(f"❌ 验证码校验失败: {val_json.get('message', '未知错误')}, 正在重试...")
        else:
            print("❌ 服务端返回的验证码获取结果异常，正在重试...")
            time.sleep(1)

    print("\n⏳ [3/4] 正在加密密码并提交登录请求...")
    encrypted_pwd = encrypt_password(PASSWORD)
    
    url_login = "https://account.court.gov.cn/api/login"
    login_headers = {
        "accept": "*/*",
        "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "sec-ch-ua": "\"Google Chrome\";v=\"149\", \"Chromium\";v=\"149\", \"Not)A;Brand\";v=\"24\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "x-requested-with": "XMLHttpRequest",
        "referer": app_url,   # ← 同样用完整 app?back_url=... referrer
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
    }
    
    # 携带经过校验的 bizToken 和 imgVerifyToken 以通过登录验证
    data = {
        "username": USERNAME,
        "password": encrypted_pwd,
        "bizToken": session_id,
        "imgVerifyToken": session_id,
        "appDomain": "wenshu.court.gov.cn"
    }
    
    try:
        resp = session.post(url_login, headers=login_headers, data=data, proxies=PROXIES, timeout=10)
        res_json = resp.json()
    except Exception as e:
        print(f"❌ 登录请求失败: {e}")
        sys.exit(1)
        
    if res_json.get("success") or str(res_json.get("code")) in ["0", "000000"]:
        print(f"🎉 登录成功！响应数据: {res_json}")
        print("📋 登录成功后的 Headers:")
        for k, v in resp.headers.items():
            print(f"  {k}: {v}")
        print("🍪 登录成功后的 Cookies:")
        _cookie_dump(session.cookies)
    else:
        print(f"❌ 登录失败: {res_json.get('message')}")
        print(f"调试信息: {res_json}")
        sys.exit(1)
        
    # =========================================================================
    # 🔑 关键步骤：login 成功后，HOLDONKEY 已变为已认证态。
    # 但原 oauth_url 的 state/signature 是在旧（未认证）HOLDONKEY 上下文生成的，
    # 直接使用可能导致 OAuth 服务器颁发无效 code。
    # 解决方案：重新调用 tongyiLogin/authorize 获取新鲜 OAuth URL（state/signature 匹配当前会话）
    # =========================================================================
    print("\n🔄 [关键] 登录成功，正在用已认证会话重新获取 OAuth 授权 URL...")
    import re
    old_state = re.search(r'state=([^&]+)', oauth_url)
    old_state = old_state.group(1)[:16] if old_state else '?'
    print(f"  旧 OAuth URL state: {old_state}...")

    try:
        refresh_headers = {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "sec-ch-ua": "\"Google Chrome\";v=\"149\", \"Chromium\";v=\"149\", \"Not)A;Brand\";v=\"24\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "x-requested-with": "XMLHttpRequest",
            "referer": "https://wenshu.court.gov.cn/website/wenshu/181010CARHS5BS3C/index.html?open=login"
        }
        refresh_resp = session.post(
            "https://wenshu.court.gov.cn/tongyiLogin/authorize",
            headers=refresh_headers, proxies=PROXIES, timeout=10
        )
        fresh_oauth_url = refresh_resp.text.strip()
        if fresh_oauth_url.startswith("http"):
            new_state = re.search(r'state=([^&]+)', fresh_oauth_url)
            new_state = new_state.group(1)[:16] if new_state else '?'
            print(f"  新 OAuth URL state: {new_state}...")
            print(f"  ✅ 已获取新鲜 OAuth URL，将使用新 URL 进行回调")
            oauth_url = fresh_oauth_url  # ← 替换为新鲜 URL
            # 同时更新 app_referer
            app_url = f"https://account.court.gov.cn/app?back_url={urllib.parse.quote(oauth_url, safe='')}"
        else:
            print(f"  ⚠️ 获取新 OAuth URL 失败({fresh_oauth_url[:80]})，回退使用旧 URL")
    except Exception as e:
        print(f"  ⚠️ 获取新 OAuth URL 异常({e})，回退使用旧 URL")

    print("\n🚀 [4/4] 正在用已认证 HOLDONKEY 访问 OAuth 链接，自动跟踪跳转获取 wenshu Session...")
    app_referer = f"https://account.court.gov.cn/app?back_url={urllib.parse.quote(oauth_url, safe='')}"

    # 与支付宝扫码流程保持一致：用 allow_redirects=True 完整跟踪跳转链
    # 服务端看到已认证的 HOLDONKEY → 颁发 code → 302 到 CallBackController → 设置 SESSION → 302 到首页
    exchange_headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "upgrade-insecure-requests": "1",
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "navigate",
        "sec-fetch-dest": "document",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "referer": app_referer
    }
    holdonkey_val = session.cookies.get('HOLDONKEY', domain='account.court.gov.cn')
    print(f"  当前 HOLDONKEY: {holdonkey_val[:16] if holdonkey_val else '(空)'}...")
    print(f"  OAuth URL 前80字符: {oauth_url[:80]}...")

    cb_resp = session.get(oauth_url, headers=exchange_headers, proxies=PROXIES,
                          allow_redirects=True, timeout=15)

    print(f"🏁 授权跳转最终落地页: {cb_resp.url}")
    print(f"📋 跳转历史({len(cb_resp.history)}步):")
    for i, r in enumerate(cb_resp.history):
        set_cookie = r.headers.get('Set-Cookie', '(无 Set-Cookie)')
        print(f"  [{i+1}] HTTP {r.status_code} → {r.url[:80]}")
        print(f"       Set-Cookie: {set_cookie[:120]}")
    print(f"  [最终] HTTP {cb_resp.status_code} → {cb_resp.url[:80]}")
    print(f"         Set-Cookie: {cb_resp.headers.get('Set-Cookie', '(无 Set-Cookie)')}")

    print(f"\n📄 === CallBack 响应完整文本 (前800字) ===")
    print(cb_resp.text[:800])
    print("=== 响应文本结束 ===\n")

    # 提取落地页 URL
    landing_match = re.search(r"window\.open\s*\(\s*['\"]([^'\"]+)['\"]", cb_resp.text)
    loc_match = re.search(r"(?:location\.href|window\.location)\s*=\s*['\"]([^'\"]+)['\"]", cb_resp.text)
    landing_url = cb_resp.url  # 默认使用最终落地页
    if landing_match or loc_match:
        m = landing_match or loc_match
        landing_path = m.group(1)
        landing_url = "https://wenshu.court.gov.cn" + landing_path if landing_path.startswith("/") else landing_path
        print(f"\n🚀 [关键步骤] 正在访问 OAuth 最终落地页以激活服务端会话权限: {landing_url}")
        landing_headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "upgrade-insecure-requests": "1",
            "referer": cb_resp.url,
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
        }
        landing_resp = session.get(landing_url, headers=landing_headers, proxies=PROXIES, timeout=15)
        print(f"✅ 落地页激活响应状态: HTTP {landing_resp.status_code}")
        print(f"   Set-Cookie: {landing_resp.headers.get('Set-Cookie', '(无)')}")
    else:
        print("⚠️ 未找到 window.open/location.href 跳转目标，以 final_url 作为 landing_url")
    
    print(f"\n🍪 访问落地页后 session 中所有 Cookie:")
    _cookie_dump(session.cookies)

    print(f"\n🔍 立即验证登录态（当前内存 session）...")
    chk_headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "referer": landing_url,
        "x-requested-with": "XMLHttpRequest",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    chk_resp = session.post(
        "https://wenshu.court.gov.cn/website/parse/rest.q4w",
        headers=chk_headers,
        data={"cfg": "com.lawyee.wbsttools.web.parse.dto.AppUserDTO@currentUser"},
        proxies=PROXIES, timeout=10
    )
    try:
        chk_json = chk_resp.json()
        print(f"  [Debug] Raw currentUser response: {chk_resp.text[:300]}")
        result_obj = chk_json.get("result", {})
        # 登录态：result 为 {"userName": "xxx"} 形式，或旧格式 {"userId": "xxx", ...}
        if isinstance(result_obj, dict):
            user_name = result_obj.get("userName") or result_obj.get("userId") or result_obj.get("loginId")
        else:
            user_name = str(result_obj)
        
        if not user_name or "anonymous" in str(user_name).lower():
            print("  ❌ 警告: Session 未绑定用户，登录验证失败！")
            print("  💡 可能原因: (1) ncCookie 缺失导致登录被 WAF 拦截")
            print("             (2) SESSION 被覆盖（tongyiLogin 和 account 跳转冲突）")
            print("             (3) HOLDONKEY 与 OAuth state 不匹配")
        else:
            print(f"  🎉 登录验证通过! userName = {user_name}")
    except Exception as e:
        print(f"  [Debug] Failed to parse currentUser: {e}")
        print(f"  [Debug] Raw response: {chk_resp.text}")
    

    # 保存 Cookie（兼容 curl_cffi 和 requests）
    final_cookies = {}
    for c in session.cookies:
        domain = _cookie_attr(session.cookies, c, "domain")
        name = _cookie_attr(session.cookies, c, "name")
        value = _cookie_attr(session.cookies, c, "value")
        if "wenshu" in str(domain) or domain == ".court.gov.cn":
            final_cookies[name] = value
    
    session_data = {
        "username": USERNAME,
        "cookies": final_cookies,
        "timestamp": int(time.time()),
        "oauth_url": oauth_url,
        "final_url": cb_resp.url,
        "landing_url": landing_url
    }
    
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(session_data, f, indent=2, ensure_ascii=False)
    print(f"\n💾 文书网正式登录 Cookie 已持久化保存至: {SESSION_FILE}")
    print("📋 当前抓取到的文书网核心 Cookie 列表：")
    for k, v in final_cookies.items():
        print(f"  ▪ {k}: {v}")
    
    # ⚡ 立即在相同 session 会话中发起实时文书检索与解密测试，防止会话过期或参数错误
    print("\n⚡ [Debug] 正在当前会话中发起实时检索与解密测试...")
    try:
        from utils.wenshu_crypto import generate_random_salt, encrypt_ciphertext, decrypt_result
        from datetime import datetime
        
        now = datetime.now()
        date_str = now.strftime("%Y%m%d")
        timestamp_ms = int(time.time() * 1000)
        salt = generate_random_salt(24)
        ciphertext = encrypt_ciphertext(timestamp_ms, salt, date_str)
        token = generate_random_salt(24)
        
        url = "https://wenshu.court.gov.cn/website/parse/rest.q4w"
        headers = {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "referer": landing_url if landing_url else "https://wenshu.court.gov.cn/website/wenshu/181217BMTKHNT2W0/index.html?",
            "x-requested-with": "XMLHttpRequest",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
        }
        
        # 先测试 currentUser 接口检查登录态
        user_data = {
            "ciphertext": ciphertext,
            "cfg": "com.lawyee.wbsttools.web.parse.dto.AppUserDTO@currentUser",
            "__RequestVerificationToken": token
        }
        u_resp = session.post(url, headers=headers, data=user_data, proxies=PROXIES, timeout=10)
        print(f"  [Debug] 当前用户信息响应: {u_resp.text[:300]}")
        
        query_condition_list = [{"key": "cprq", "value": "2025-07-01 TO 2025-07-31"}]
        post_data = {
            "pageId": "a13bc47563efb138f24117bd13de74bd",
            "cprqStart": "2025-07-01",
            "cprqEnd": "2025-07-31",
            "sortFields": "s50:desc",
            "ciphertext": ciphertext,
            "pageNum": "1",
            "pageSize": "5",
            "queryCondition": json.dumps(query_condition_list, separators=(',', ':')),
            "cfg": "com.lawyee.judge.dc.parse.dto.SearchDataDsoDTO@queryDoc",
            "__RequestVerificationToken": token,
            "wh": "791",
            "ww": "1536",
            "cs": "0"
        }
        
        resp = session.post(url, headers=headers, data=post_data, proxies=PROXIES, timeout=15)
        print(f"  [Debug] 检索接口响应 Status: {resp.status_code}")
        print(f"  [Debug] 检索接口响应 Body: {resp.text[:500]}")
        
        resp_json = resp.json()
        if resp_json.get("code") == 1:
            sec_key = resp_json.get("secretKey")
            result_enc = resp_json.get("result")
            dec_data = decrypt_result(result_enc, sec_key, date_str)
            print("\n🎉 [Success] 成功在登录会话中实时解密文书数据！")
            print(f"📄 解密结果预览 (前 800 字符):\n{dec_data[:800]}\n")
        else:
            print(f"❌ 实时检索失败: {resp_json}")
    except Exception as ex:
        print(f"❌ 实时检索异常: {ex}")
        
    return session_data

if __name__ == "__main__":
    print("═" * 54)
    print("  中国裁判文书网 - 纯协议账号密码全自动登录工具")
    print("═" * 54)
    
    with _chrome_session() as s:
        oauth_url, app_url = init_oauth(s)
        login_with_password(s, oauth_url, app_url)
