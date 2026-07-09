#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
裁判文书网 - 登录抓包器 (Playwright)

功能：
  1. 打开 Chromium 浏览器，开启全量网络请求录制
  2. 用户手动完成登录（30 秒倒计时）
  3. 自动提取 SESSION + HOLDONKEY 保存到 session.json
  4. 打印关键 API 请求的完整细节（对比 Python 纯协议方案）

使用方法：
  python login_sniffer.py
  → 浏览器打开后，手动完成账号密码登录
  → 看到文书网首页显示手机号后，等待脚本自动提取 cookie
"""

import json
import os
import sys
import time
import re
from playwright.sync_api import sync_playwright

# ==============================================================================
# 配置
# ==============================================================================
PROXY_SERVER = "http://127.0.0.1:10808"

CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'config')
os.makedirs(CONFIG_DIR, exist_ok=True)
SESSION_FILE = os.path.join(CONFIG_DIR, 'session.json')
HAR_FILE = os.path.join(CONFIG_DIR, 'login_requests.json')

WENSHU_LOGIN_URL = "https://wenshu.court.gov.cn/website/wenshu/181010CARHS5BS3C/index.html?open=login"

# 我们关心的关键 API 路径
KEY_APIS = [
    "tongyiLogin/authorize",
    "captcha/getBase64",
    "captcha/validate",
    "api/login",
    "oauth/authorize",
    "CallBackController/authorizeCallBack",
    "parse/rest.q4w",
    "api/third/alipay",
]

# 要过滤掉的无关请求（图片、字体、统计等）
SKIP_URL_PATTERNS = [
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".ttf",
    "aliyuncs.com/r.png", "arms-retcode",
]


def should_log(url: str) -> bool:
    """判断请求是否值得打印"""
    for skip in SKIP_URL_PATTERNS:
        if skip in url:
            return False
    for key in KEY_APIS:
        if key in url:
            return True
    return False


def run_sniffer():
    captured_requests = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--start-maximized"],
        )
        context = browser.new_context(
            viewport={"width": 1536, "height": 960},
            proxy={"server": PROXY_SERVER} if PROXY_SERVER else None,
        )
        page = context.new_page()

        # =====================================================================
        # 开启请求/响应拦截
        # =====================================================================
        def on_request(request):
            url = request.url
            if should_log(url):
                req_info = {
                    "type": "request",
                    "url": url,
                    "method": request.method,
                    "headers": dict(request.headers),
                    "postData": request.post_data,
                    "timestamp": time.time(),
                }
                captured_requests.append(req_info)

        def on_response(response):
            url = response.url
            if should_log(url):
                try:
                    body = response.text()[:2000]  # 截断
                except Exception:
                    body = "(binary/不可读)"
                resp_info = {
                    "type": "response",
                    "url": url,
                    "status": response.status,
                    "headers": dict(response.headers),
                    "body": body,
                    "timestamp": time.time(),
                }
                captured_requests.append(resp_info)

        page.on("request", on_request)
        page.on("response", on_response)

        # =====================================================================
        # 打开登录页
        # =====================================================================
        print("═" * 60)
        print("  裁判文书网 - 登录抓包器")
        print("═" * 60)
        print()
        print("📌 浏览器即将打开，请手动完成账号密码登录。")
        print("   登录成功后（看到首页显示手机号），等待脚本自动处理。")
        print()
        print("⏳ [1/2] 正在打开文书网登录页面...")
        page.goto(WENSHU_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)

        # =====================================================================
        # 等待用户手动登录（倒计时 120 秒）
        # =====================================================================
        print()
        print("╔══════════════════════════════════════════════════╗")
        print("║  👆 请在浏览器中手动完成登录                      ║")
        print("║    脚本将在 120 秒内持续监听网络请求...          ║")
        print("╚══════════════════════════════════════════════════╝")
        print()

        start_time = time.time()
        timeout = 120
        login_detected = False

        while time.time() - start_time < timeout:
            time.sleep(2)
            elapsed = int(time.time() - start_time)
            remaining = timeout - elapsed

            # 检测是否已登录成功（URL 变为 wenshu 首页）
            current_url = page.url
            if "wenshu.court.gov.cn/website/wenshu" in current_url and \
               "open=login" not in current_url and \
               "CallBackController" not in current_url:
                # 检查页面内容是否显示用户信息
                try:
                    body = page.content()
                    if "anonymousUser" not in body and \
                       ("手机" in body or "退出" in body or "个人中心" in body or "userName" in body):
                        if not login_detected:
                            print(f"\n✅ [{elapsed}s] 检测到登录成功！当前 URL: {current_url[:80]}...")
                            login_detected = True
                            # 登录成功后多等 5 秒让 cookie 稳定
                            page.wait_for_timeout(5000)
                            break
                except Exception:
                    pass

            if elapsed % 10 == 0 and elapsed > 0:
                print(f"  ⏳ 已等待 {elapsed}s / {timeout}s... (当前 URL: {current_url[:70]}...)")

        if not login_detected:
            print(f"\n⏰ 倒计时结束（{timeout}s），将尝试提取当前 cookie...")
            page.wait_for_timeout(2000)

        # =====================================================================
        # 提取 Cookie
        # =====================================================================
        print("\n⏳ [2/2] 正在提取 cookie...")
        cookies = context.cookies()

        session_cookie = None
        holdonkey_cookie = None
        nccookie = None
        all_wenshu_cookies = {}

        for c in cookies:
            domain = c.get("domain", "")
            name = c["name"]
            value = c["value"]
            if name == "SESSION" and "wenshu" in domain:
                session_cookie = value
            if name == "HOLDONKEY" and "account" in domain:
                holdonkey_cookie = value
            if name == "ncCookie":
                nccookie = value
            if "wenshu" in domain or domain == ".court.gov.cn":
                all_wenshu_cookies[name] = value

        # =====================================================================
        # 提取 PAGE_ID — 需要先导航到搜索页触发 pageId 生成
        # =====================================================================
        print("\n⏳ 正在导航到搜索页以获取 PAGE_ID...")
        search_url = "https://wenshu.court.gov.cn/website/wenshu/181217BMTKHNT2W0/index.html"
        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)  # 等 JS 初始化完毕、pageId 生成

        page_id = None
        # 从 URL 提取（搜索页会在 URL hash 或参数中带上 pageId）
        current_url = page.url
        pid_match = re.search(r'pageId=([a-f0-9]{32})', current_url)
        if pid_match:
            page_id = pid_match.group(1)
        # fallback: 从捕获的 rest.q4w 请求中提取
        if not page_id:
            for req in captured_requests:
                pd = req.get("postData") or ""
                pid_match = re.search(r'pageId=([a-f0-9]{32})', pd)
                if pid_match:
                    page_id = pid_match.group(1)
                    break
        # fallback: 从页面 JS 变量提取
        if not page_id:
            try:
                page_id = page.evaluate("() => window.__pageId || localStorage.getItem('pageId') || ''")
            except Exception:
                pass

        print(f"\n📋 提取到的关键信息:")
        print(f"  PAGE_ID:      {page_id or '❌ 未获取到!'}")
        print(f"  SESSION:      {session_cookie or '❌ 未获取到!'}")
        print(f"  HOLDONKEY:    {holdonkey_cookie or '❌ 未获取到!'}")
        print(f"  ncCookie:     {nccookie[:20] + '...' if nccookie else '❌ 未获取到!'}")

        if not session_cookie:
            print("\n❌ 未获取到 SESSION cookie！")
            browser.close()
            sys.exit(1)

        # =====================================================================
        # 保存到 session.json
        # =====================================================================
        session_data = {
            "username": "(手动登录)",
            "page_id": page_id,
            "cookies": all_wenshu_cookies,
            "session": session_cookie,
            "holdonkey": holdonkey_cookie,
            "timestamp": int(time.time()),
        }
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2, ensure_ascii=False)
        print(f"\n💾 已保存至: {SESSION_FILE}")
        print(f"   PAGE_ID: {page_id}")
        print(f"   SESSION: {session_cookie}")
        print(f"   HOLDONKEY: {holdonkey_cookie}")

        # =====================================================================
        # 打印关键请求日志
        # =====================================================================
        print("\n" + "═" * 60)
        print("  📡 关键 API 请求/响应日志")
        print("═" * 60)

        # 按 URL 分组打印
        printed_urls = set()
        for req in captured_requests:
            url = req["url"]
            # 提取简短路径
            short_url = url
            for key in KEY_APIS:
                if key in url:
                    short_url = key
                    break
            if short_url in printed_urls:
                continue
            printed_urls.add(short_url)

            if req["type"] == "request":
                print(f"\n{'─' * 50}")
                print(f"📤 REQUEST → {req['method']} {short_url}")
                print(f"   Full URL: {url[:120]}...")
                # 只打印关键 headers
                key_headers = ["content-type", "referer", "x-requested-with",
                               "sec-fetch-site", "sec-fetch-mode", "sec-fetch-dest",
                               "cookie", "set-cookie"]
                for kh in key_headers:
                    for hk, hv in req.get("headers", {}).items():
                        if kh in hk.lower():
                            val = hv[:100] if len(str(hv)) > 100 else hv
                            print(f"   Header {hk}: {val}")
                if req.get("postData"):
                    pd = req["postData"][:200]
                    print(f"   Body: {pd}")

            elif req["type"] == "response":
                print(f"   📥 RESPONSE ← HTTP {req['status']}")
                # 找 set-cookie
                for hk, hv in req.get("headers", {}).items():
                    if "set-cookie" in hk.lower():
                        print(f"   Set-Cookie: {hv[:150]}")
                body = req.get("body", "")
                if body and len(body) < 500:
                    print(f"   Body: {body}")

        # 保存完整请求日志
        with open(HAR_FILE, "w", encoding="utf-8") as f:
            json.dump(captured_requests, f, indent=2, ensure_ascii=False)
        print(f"\n📁 完整请求日志已保存至: {HAR_FILE}")
        print(f"   ({len(captured_requests)} 条记录)")

        # =====================================================================
        # 用提取的 cookie 做一次快速验证
        # =====================================================================
        print("\n" + "═" * 60)
        print("  🔍 立即验证登录态...")
        print("═" * 60)
        try:
            import requests as req_lib
            sess = req_lib.Session()
            sess.cookies.set("SESSION", session_cookie, domain="wenshu.court.gov.cn")
            if holdonkey_cookie:
                sess.cookies.set("HOLDONKEY", holdonkey_cookie, domain="account.court.gov.cn")

            resp = sess.post(
                "https://wenshu.court.gov.cn/website/parse/rest.q4w",
                headers={
                    "accept": "application/json, text/javascript, */*; q=0.01",
                    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "referer": "https://wenshu.court.gov.cn/website/wenshu/181217BMTKHNT2W0/index.html?",
                    "x-requested-with": "XMLHttpRequest",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
                data={"cfg": "com.lawyee.wbsttools.web.parse.dto.AppUserDTO@currentUser"},
                proxies={"http": PROXY_SERVER, "https": PROXY_SERVER} if PROXY_SERVER else None,
                timeout=10
            )
            result = resp.json()
            user_info = result.get("result", {})
            if isinstance(user_info, dict):
                name = user_info.get("userName") or user_info.get("realName") or user_info.get("userId")
                if name and "anonymous" not in str(name).lower():
                    print(f"  🎉 登录验证成功! 当前用户: {name}")
                else:
                    print(f"  ❌ Session 未认证: {resp.text[:200]}")
            else:
                print(f"  Raw: {resp.text[:200]}")
        except Exception as e:
            print(f"  ❌ 验证异常: {e}")

        print("\n✅ 抓包完成！浏览器即将关闭...")
        page.wait_for_timeout(2000)
        browser.close()


if __name__ == "__main__":
    run_sniffer()
