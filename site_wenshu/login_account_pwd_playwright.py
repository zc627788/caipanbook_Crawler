#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
裁判文书网 - 账号密码登录（Playwright 浏览器自动化 + requests 混合方案）

策略：
  1. Playwright 打开真实 Chromium 浏览器 → 完整走登录流程（自然绕过反调试 JS）
  2. 登录成功后提取 SESSION + HOLDONKEY cookie
  3. 保存到 config/session.json，后续用 requests 搜文书

为什么不用纯协议？
  CallBackController 页面有反调试 JS，F12 开着就会阻断 session 绑定。
  Python requests 完全不执行 JS，跳过了关键激活逻辑，导致 SESSION 始终 anonymous。
"""

import json
import os
import sys
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ==============================================================================
# 配置
# ==============================================================================
USERNAME = "63-9568348610"
PASSWORD = "Zc627788***"

PROXY_SERVER = "http://127.0.0.1:10808"  # Playwright 代理

CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'config')
os.makedirs(CONFIG_DIR, exist_ok=True)
SESSION_FILE = os.path.join(CONFIG_DIR, 'session.json')

# 文书网登录入口
WENSHU_LOGIN_URL = "https://wenshu.court.gov.cn/website/wenshu/181010CARHS5BS3C/index.html?open=login"


def run_login():
    """
    用 Playwright 打开浏览器，完成账号密码登录，返回 (session_cookie, holdonkey_cookie)
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,  # ← 必须可见：要人工输入验证码
            args=["--start-maximized"],
        )
        context = browser.new_context(
            viewport={"width": 1536, "height": 960},
            proxy={"server": PROXY_SERVER} if PROXY_SERVER else None,
        )
        page = context.new_page()

        # =====================================================================
        # Step 1: 打开文书网 → 通过 API 获取 OAuth URL → 导航到 account 登录页
        # =====================================================================
        print("⏳ [1/5] 正在打开文书网并调用 tongyiLogin/authorize 获取 OAuth 跳转链接...")
        page.goto(WENSHU_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)  # 等 JS 初始化完毕

        # 在浏览器 JS 环境里直接调 tongyiLogin/authorize（与浏览器行为完全一致）
        oauth_url = page.evaluate("""
            async () => {
                const resp = await fetch("https://wenshu.court.gov.cn/tongyiLogin/authorize", {
                    method: "POST",
                    headers: {
                        "accept": "*/*",
                        "x-requested-with": "XMLHttpRequest",
                        "referer": "https://wenshu.court.gov.cn/website/wenshu/181010CARHS5BS3C/index.html?open=login"
                    },
                    credentials: "omit"
                });
                return await resp.text();
            }
        """)
        oauth_url = oauth_url.strip()
        print(f"  OAuth URL: {oauth_url[:100]}...")
        if not oauth_url.startswith("http"):
            print(f"❌ 获取 OAuth URL 失败: {oauth_url}")
            page.screenshot(path=os.path.join(CONFIG_DIR, "debug_oauth.png"))
            browser.close()
            sys.exit(1)

        # 构造 account 登录页 URL 并导航
        import urllib.parse
        account_login_url = f"https://account.court.gov.cn/app?back_url={urllib.parse.quote(oauth_url, safe='')}"
        print(f"⏳ [2/5] 正在导航到 account 统一登录页...")
        page.goto(account_login_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        current_url = page.url
        print(f"  当前 URL: {current_url[:100]}...")

        # =====================================================================
        # Step 3: 等待登录表单加载
        # =====================================================================
        print("⏳ [3/5] 等待登录表单加载...")
        page.wait_for_timeout(2000)

        # 尝试找到验证码图片
        try:
            page.wait_for_selector("img[src*='captcha'], img[src*='getBase64'], img.captcha, .captcha img, #captchaImg", timeout=10000)
            print("  ✅ 验证码图片已加载")
        except PlaywrightTimeout:
            print("  ⚠️ 未找到验证码图片，尝试截图查看页面状态...")
            page.screenshot(path=os.path.join(CONFIG_DIR, "debug_captcha.png"))
            print(f"  截图: {os.path.join(CONFIG_DIR, 'debug_captcha.png')}")

        # =====================================================================
        # Step 4: 人工识别验证码
        # =====================================================================
        print("\n🖼️ [4/5] 请查看浏览器窗口中的验证码图片...")
        # 截图方便查看
        page.screenshot(path=os.path.join(CONFIG_DIR, "login_form.png"))
        print(f"  登录页截图已保存: {os.path.join(CONFIG_DIR, 'login_form.png')}")
        captcha_text = input("💡 请输入验证码图片中的文字: ").strip()

        # =====================================================================
        # Step 5: 填写表单并提交
        # =====================================================================
        print("⏳ [5/5] 正在填写登录表单...")

        # 定位验证码输入框（尝试多种选择器）
        captcha_input = None
        for selector in [
            "input[placeholder*='验证码']",
            "input[name*='captcha']",
            "input[name*='verify']",
            "input.captcha-input",
            "input[type='text']",  # fallback: 第一个文本输入框通常是验证码
        ]:
            try:
                captcha_input = page.wait_for_selector(selector, timeout=3000)
                if captcha_input:
                    break
            except PlaywrightTimeout:
                continue

        if captcha_input:
            captcha_input.click()
            captcha_input.fill(captcha_text)
            print(f"  ✅ 已填入验证码: {captcha_text}")
        else:
            print("  ⚠️ 未自动找到验证码输入框，请手动在浏览器中输入验证码")
            input("  手动输入完成后按 Enter 继续...")

        # 定位用户名和密码输入框
        # 账号密码登录区域可能在「账号登录」tab 里，先尝试点击 tab
        try:
            account_tab = page.wait_for_selector(
                "text=账号登录, text=帐号登录, text=密码登录, .account-login, [data-type='account']",
                timeout=3000
            )
            if account_tab:
                account_tab.click()
                page.wait_for_timeout(500)
                print("  ✅ 已切换到账号登录 tab")
        except PlaywrightTimeout:
            pass  # 可能已经在账号登录 tab

        # 填用户名
        username_input = None
        for selector in [
            "input[placeholder*='手机'], input[placeholder*='账号'], input[placeholder*='用户名']",
            "input[name='username'], input[name='mobile'], input[name='account']",
            "input[type='text']:not([placeholder*='验证码'])",
        ]:
            try:
                # 找所有匹配的 input，选第一个非验证码的
                candidates = page.query_selector_all(selector)
                for c in candidates:
                    ph = c.get_attribute("placeholder") or ""
                    if "验证码" not in ph and "captcha" not in ph.lower():
                        username_input = c
                        break
                if username_input:
                    break
            except Exception:
                continue

        if username_input:
            username_input.click()
            username_input.fill(USERNAME)
            print(f"  ✅ 已填入用户名: {USERNAME}")
        else:
            print("  ⚠️ 未自动找到用户名输入框，请手动输入")
            input("  手动输入完成后按 Enter 继续...")

        # 填密码
        password_input = None
        for selector in [
            "input[type='password']",
            "input[placeholder*='密码']",
            "input[name='password']",
        ]:
            try:
                password_input = page.wait_for_selector(selector, timeout=3000)
                if password_input:
                    break
            except PlaywrightTimeout:
                continue

        if password_input:
            password_input.click()
            password_input.fill(PASSWORD)
            print(f"  ✅ 已填入密码")
        else:
            print("  ⚠️ 未自动找到密码输入框，请手动输入")
            input("  手动输入完成后按 Enter 继续...")

        # =====================================================================
        # Step 6: 点击登录按钮并等待跳转
        # =====================================================================
        print("⏳ [6/6] 正在提交登录...")

        # 点击登录按钮
        login_btn = None
        for selector in [
            "button:has-text('登录')",
            "button:has-text('登 录')",
            "input[type='submit'][value*='登录']",
            "button[type='submit']",
            ".login-btn",
            "#loginBtn",
        ]:
            try:
                login_btn = page.wait_for_selector(selector, timeout=3000)
                if login_btn:
                    break
            except PlaywrightTimeout:
                continue

        if login_btn:
            login_btn.click()
            print("  ✅ 已点击登录按钮")
        else:
            print("  ⚠️ 未找到登录按钮，请手动点击登录")
            input("  点击完成后按 Enter 继续...")

        # 等待登录完成，页面跳转回 wenshu
        print("  ⏳ 等待登录跳转...")
        try:
            # 等待 URL 变为 wenshu 首页（包含 website/wenshu）
            page.wait_for_url("**wenshu.court.gov.cn/website/wenshu/**", timeout=30000)
            print(f"  ✅ 已跳转回文书网首页: {page.url[:80]}...")
        except PlaywrightTimeout:
            print(f"  ⚠️ 登录跳转超时，当前 URL: {page.url[:100]}")
            # 检查是否登录成功（页面上是否有用户信息）
            page.screenshot(path=os.path.join(CONFIG_DIR, "after_login.png"))
            print(f"  截图: {os.path.join(CONFIG_DIR, 'after_login.png')}")

        # 等页面完全加载
        page.wait_for_timeout(3000)

        # =====================================================================
        # 检查登录结果
        # =====================================================================
        page_content = page.content()
        if USERNAME.split("-")[-1] in page_content or "退出" in page_content or "个人中心" in page_content:
            print("🎉 登录成功！页面显示用户信息")
        else:
            print("⚠️ 页面未显示用户信息，可能登录失败或需要额外操作")
            page.screenshot(path=os.path.join(CONFIG_DIR, "login_result.png"))
            print(f"  截图: {os.path.join(CONFIG_DIR, 'login_result.png')}")
            # 不退出，因为 cookie 可能已经设置好了

        # =====================================================================
        # 提取 Cookie
        # =====================================================================
        cookies = context.cookies()
        session_cookie = None
        holdonkey_cookie = None
        all_wenshu_cookies = {}

        for c in cookies:
            if c["name"] == "SESSION" and "wenshu" in c.get("domain", ""):
                session_cookie = c["value"]
            if c["name"] == "HOLDONKEY" and "account" in c.get("domain", ""):
                holdonkey_cookie = c["value"]
            if "wenshu" in c.get("domain", "") or c.get("domain", "") == ".court.gov.cn":
                all_wenshu_cookies[c["name"]] = c["value"]

        print(f"\n📋 提取到的 Cookie:")
        print(f"  SESSION:    {session_cookie or '(未获取到!)'}")
        print(f"  HOLDONKEY:  {holdonkey_cookie or '(未获取到!)'}")
        print(f"  全部 wenshu 域 Cookie: {all_wenshu_cookies}")

        if not session_cookie:
            print("\n❌ 未获取到 SESSION cookie！请确认登录是否成功。")
            input("按 Enter 关闭浏览器...")
            browser.close()
            sys.exit(1)

        # =====================================================================
        # 持久化保存
        # =====================================================================
        session_data = {
            "username": USERNAME,
            "cookies": all_wenshu_cookies,
            "session": session_cookie,
            "holdonkey": holdonkey_cookie,
            "timestamp": int(time.time()),
        }

        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Cookie 已保存至: {SESSION_FILE}")

        # 保持浏览器打开几秒让用户确认
        print("\n⏳ 5 秒后自动关闭浏览器...")
        page.wait_for_timeout(5000)
        browser.close()

        return session_cookie, holdonkey_cookie


def verify_and_search(session_cookie, holdonkey_cookie):
    """
    用提取的 cookie 做一次实时检索验证
    """
    import requests
    from utils.wenshu_crypto import generate_random_salt, encrypt_ciphertext, decrypt_result
    from datetime import datetime

    PROXIES_REQUESTS = {
        'http': 'http://127.0.0.1:10808',
        'https': 'http://127.0.0.1:10808'
    }

    sess = requests.Session()
    sess.cookies.set("SESSION", session_cookie, domain="wenshu.court.gov.cn")
    if holdonkey_cookie:
        sess.cookies.set("HOLDONKEY", holdonkey_cookie, domain="account.court.gov.cn")

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
        "referer": "https://wenshu.court.gov.cn/website/wenshu/181217BMTKHNT2W0/index.html?",
        "x-requested-with": "XMLHttpRequest",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    # 验证 currentUser
    print("\n🔍 验证登录态 (currentUser)...")
    user_data = {
        "ciphertext": ciphertext,
        "cfg": "com.lawyee.wbsttools.web.parse.dto.AppUserDTO@currentUser",
        "__RequestVerificationToken": token
    }
    u_resp = sess.post(url, headers=headers, data=user_data, proxies=PROXIES_REQUESTS, timeout=10)
    try:
        u_json = u_resp.json()
        result = u_json.get("result", {})
        if isinstance(result, dict):
            user_name = result.get("userName") or result.get("realName") or result.get("userId")
            if user_name and "anonymous" not in str(user_name).lower():
                print(f"  🎉 登录验证通过! 当前用户: {user_name}")
            else:
                print(f"  ❌ Session 未认证: {u_resp.text[:200]}")
                return
    except Exception as e:
        print(f"  ❌ 解析 currentUser 失败: {e}")
        print(f"  Raw: {u_resp.text[:200]}")
        return

    # 检索测试
    print("\n⚡ 实时检索测试...")
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
    resp = sess.post(url, headers=headers, data=post_data, proxies=PROXIES_REQUESTS, timeout=15)
    resp_json = resp.json()
    if resp_json.get("code") == 1:
        sec_key = resp_json.get("secretKey")
        result_enc = resp_json.get("result")
        dec_data = decrypt_result(result_enc, sec_key, date_str)
        print(f"  🎉 检索成功！解密结果预览:\n{dec_data[:500]}\n")
    else:
        print(f"  ❌ 检索失败: {resp_json}")


if __name__ == "__main__":
    print("═" * 54)
    print("  中国裁判文书网 - 账号密码登录 (Playwright 混合方案)")
    print("═" * 54)
    print()
    print("📌 说明: 将打开 Chromium 浏览器，请在浏览器中查看验证码并在此输入。")
    print("   登录成功后会自动提取 cookie 供后续 requests 使用。")
    print()

    session_val, holdonkey_val = run_login()

    if session_val:
        print("\n" + "═" * 54)
        print("  正在用提取的 cookie 验证...")
        print("═" * 54)
        verify_and_search(session_val, holdonkey_val)
