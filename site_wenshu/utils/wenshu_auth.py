#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证：通过 curl_cffi 原生发送 /api/login + OAuth 回调，
让最终的 SESSION 彻底绑定到 curl_cffi (chrome120) 的 TLS 指纹中，
解密为什么之前 crawler_wenshu.py 会返回 code-9 与匿名问题！
"""
import json
import time
import sys
import base64
import urllib.parse
from pathlib import Path
from curl_cffi import requests as cr
from playwright.sync_api import sync_playwright
import ddddocr
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

BASE_DIR = Path(__file__).parent
CONFIG_DIR = BASE_DIR / "config"
SESSION_FILE = CONFIG_DIR / "session.json"

RSA_PUB_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA5GVku07yXCndaMS1evPIPyWwhbdWMVRqL4qg4OsKbzyTGmV4YkG8H0hwwrFLuPhqC5tL136aaizuL/lN5DRRbePct6syILOLLCBJ5J5rQyGr00l1zQvdNKYp4tT5EFlqw8tlPkibcsd5Ecc8sTYa77HxNeIa6DRuObC5H9t85ALJyDVZC3Y4ES/u61Q7LDnB3kG9MnXJsJiQxm1pLkE7Zfxy29d5JaXbbfwhCDSjE4+dUQoq2MVIt2qVjZSo5Hd/bAFGU1Lmc7GkFeLiLjNTOfECF52ms/dks92Wx/glfRuK4h/fcxtGB4Q2VXu5k68e/2uojs6jnFsMKVe+FVUDkQIDAQAB
-----END PUBLIC KEY-----"""

def encrypt_pwd(plain: str) -> str:
    rsa_key = RSA.importKey(RSA_PUB_KEY)
    cipher = PKCS1_v1_5.new(rsa_key)
    enc = cipher.encrypt(plain.encode('utf-8'))
    return urllib.parse.quote(base64.b64encode(enc).decode('utf-8'))

USERNAME_FULL = "63-9568348610"
PHONE_NUMBER  = "9568348610"
PASSWORD      = "Zc627788***"
PROXY_SERVER  = "http://127.0.0.1:10808"

def wait_for_form(page, timeout=25):
    print(f"  ⏳ 等待登录表单 (最多 {timeout}s)...")
    for i in range(timeout):
        try:
            page.wait_for_selector("input[name='username']", timeout=1000)
            page.wait_for_selector("img.captcha-img", timeout=1000)
            print(f"  ✅ 表单已加载 (耗时 {i+1}s)")
            return True
        except Exception:
            if i % 5 == 4:
                print(f"    已等待 {i+1}s... 当前 URL: {page.url[:80]}")
            continue
    return False

def login_account(username: str, password: str, proxy: str = PROXY_SERVER, max_retries: int = 3) -> dict:
    """
    针对指定用户名密码，执行完整的协议优先登录与 OAuth 回调闭环绑定，
    返回包含 session, holdonkey 与用户信息的结果字典。
    """
    for global_try in range(1, max_retries + 1):
        print(f"\n⚙️  [账号自愈/登录] 开始为账号 {username} 执行登录与会话绑定 (第 {global_try}/{max_retries} 轮)...")
        s = cr.Session(impersonate="chrome120")
        if proxy:
            s.proxies = {"http": proxy, "https": proxy}

        # 1. 获取 OAuth URL
        print("  ⏳ [1/5] curl_cffi 获取 OAuth URL...")
        try:
            r_auth = s.post(
                "https://wenshu.court.gov.cn/tongyiLogin/authorize",
                headers={
                    "accept": "*/*",
                    "x-requested-with": "XMLHttpRequest",
                    "referer": "https://wenshu.court.gov.cn/website/wenshu/181010CARHS5BS3C/index.html?open=login",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                },
                timeout=15
            )
            oauth_url = r_auth.text.strip()
            if not oauth_url.startswith("http"):
                print(f"  ⚠️ 获取的 oauth_url 异常: {oauth_url}")
                continue
            print(f"  ✅ 成功获取 OAuth URL")
        except Exception as e:
            print(f"  ⚠️ 获取 oauth_url 失败: {e}")
            continue

        # 2. Playwright 提取表单 token 与验证码图片
        print("  ⏳ [2/5] Playwright 提取登录表单 token 与验证码图片...")
        enc_pwd = encrypt_pwd(password)
        ocr = ddddocr.DdddOcr(show_ad=False)
        login_success = False

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False, args=["--start-maximized"])
                context = browser.new_context(proxy={"server": proxy} if proxy else None)
                page = context.new_page()
                page.goto(oauth_url, wait_until="domcontentloaded", timeout=30000)
                
                if not wait_for_form(page, timeout=25):
                    print("  ❌ 登录表单加载超时")
                    browser.close()
                    continue
                    
                page.wait_for_timeout(1000)

                # 把 Playwright 获得的初始化 cookie 同步给 curl_cffi Session
                for c in context.cookies():
                    s.cookies.set(c["name"], c["value"], domain=c.get("domain", ""))

                for attempt in range(1, 6):
                    token = page.evaluate("() => { const el = document.querySelector('input[name=\"token\"]'); return el ? (el.value || '') : ''; }")
                    b64_img = page.evaluate("() => { const img = document.querySelector('img.captcha-img'); return img ? (img.src || '') : ''; }")
                    if b64_img and "," in b64_img:
                        img_bytes = base64.b64decode(b64_img.split(",", 1)[1])
                        ans = ocr.classification(img_bytes).strip()
                        if len(ans) >= 3:
                            print(f"    第 {attempt} 次 OCR 识别验证码 -> '{ans}'")
                            body = urllib.parse.urlencode({
                                "username": username,
                                "password": enc_pwd,
                                "bizToken": token,
                                "imgVerifyToken": token,
                                "appDomain": "wenshu.court.gov.cn",
                                "captcha": ans
                            })
                            r_login = s.post(
                                "https://account.court.gov.cn/api/login",
                                headers={
                                    "accept": "*/*",
                                    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                                    "x-requested-with": "XMLHttpRequest",
                                    "referer": page.url,
                                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                                },
                                data=body,
                                timeout=15
                            )
                            login_res = r_login.json()
                            print(f"    📡 登录返回: {json.dumps(login_res, ensure_ascii=False)[:100]}")
                            if login_res.get("success") or login_res.get("code") == "000000":
                                print("    🎉 curl_cffi 登录成功！")
                                login_success = True
                                break
                    page.evaluate("() => { const img = document.querySelector('img.captcha-img'); if(img) img.click(); }")
                    page.wait_for_timeout(1000)
                browser.close()
        except Exception as e:
            print(f"  ⚠️ Playwright 阶段异常: {e}")
            continue

        if not login_success:
            print("  ⚠️ 本轮 OCR 或表单提交未成功，准备重试...")
            time.sleep(2)
            continue

        # 3. 执行 OAuth 302 回调跳转
        print("  ⏳ [3/5] curl_cffi 原生执行 OAuth 回调跳转...")
        try:
            r_cb = s.get(oauth_url, allow_redirects=True, timeout=20)
            print(f"  ✅ 回调落地 URL: {r_cb.url[:80]}...")
        except Exception as e:
            print(f"  ⚠️ 回调跳转失败: {e}")
            continue

        sess_val = s.cookies.get("SESSION", domain="wenshu.court.gov.cn") or s.cookies.get("SESSION")
        holdon_val = s.cookies.get("HOLDONKEY", domain="account.court.gov.cn") or s.cookies.get("HOLDONKEY")
        print(f"  👉 获得专属 SESSION:   {sess_val}")
        print(f"  👉 获得专属 HOLDONKEY: {holdon_val}")

        # 4. 验证 currentUser
        print("  ⏳ [4/5] 验证 currentUser...")
        try:
            r_user = s.post(
                "https://wenshu.court.gov.cn/website/parse/rest.q4w",
                headers={
                    "accept": "application/json, text/javascript, */*; q=0.01",
                    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "x-requested-with": "XMLHttpRequest",
                    "referer": "https://wenshu.court.gov.cn/website/wenshu/181217BMTKHNT2W0/index.html",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                },
                data={"cfg": "com.lawyee.wbsttools.web.parse.dto.AppUserDTO@currentUser"},
                timeout=15
            )
            j_user = r_user.json()
            u_res = j_user.get("result", {}) if isinstance(j_user.get("result"), dict) else {}
            real_name = u_res.get("userName") or u_res.get("realName") or u_res.get("userId")
            print(f"  📡 验证返回用户名: {real_name}")
        except Exception as e:
            print(f"  ⚠️ 验证请求失败: {e}")
            continue

        if sess_val and "anonymous" not in str(real_name).lower() and "匿名" not in str(real_name):
            print("  ✅ 登录与会话绑定彻底成功！")
            return {
                "success": True,
                "username": str(real_name),
                "session": sess_val,
                "holdonkey": holdon_val,
                "timestamp": int(time.time()),
                "all_cookies": {k: {"value": v} for k, v in s.cookies.items()}
            }
        else:
            print(f"  ⚠️ 验证结果未达到实名 ({real_name})，重试下一轮...")
            time.sleep(2)

    return {"success": False, "error": "经历多次重试后仍未成功签发有效会话"}

def main():
    print("═" * 60)
    print("  测试：协议优先 (curl_cffi 原生完成 /api/login + OAuth 闭环)")
    print("═" * 60)
    res = login_account(USERNAME_FULL, PASSWORD, PROXY_SERVER)
    if res.get("success"):
        sdata = {
            "username": res["username"],
            "session": res["session"],
            "holdonkey": res["holdonkey"],
            "timestamp": res["timestamp"],
            "all_cookies": res["all_cookies"]
        }
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(sdata, f, ensure_ascii=False, indent=2)
        print(f"\n🎉 成功！已将完全绑定给 curl_cffi 的凭据写入 session.json！")
    else:
        print(f"\n❌ 登录失败: {res.get('error')}")

if __name__ == "__main__":
    main()
