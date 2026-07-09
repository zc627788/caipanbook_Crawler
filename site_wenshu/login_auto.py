#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
裁判文书网 - 全自动账号密码登录 v2 (Playwright + ddddocr OCR)

完全对齐浏览器行为：
  1. 打开 wenshu → 调 tongyiLogin/authorize 拿 OAuth URL
  2. 导航到 oauth/authorize（让它 302 跳到 account 页面带 #/login）
  3. 等待登录表单 → 选国家码 +63 → 填账号密码
  4. ddddocr 识别验证码 → 填入 → 点登录
  5. 失败自动重试（刷新验证码）
  6. 成功后拿 PAGE_ID + SESSION + HOLDONKEY
"""

import json, os, sys, time, re, base64, urllib.parse
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import ddddocr
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

# 前端 RSA 公钥（从 login_account_pwd.py）
RSA_PUB_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA5GVku07yXCndaMS1evPIPyWwhbdWMVRqL4qg4OsKbzyTGmV4YkG8H0hwwrFLuPhqC5tL136aaizuL/lN5DRRbePct6syILOLLCBJ5J5rQyGr00l1zQvdNKYp4tT5EFlqw8tlPkibcsd5Ecc8sTYa77HxNeIa6DRuObC5H9t85ALJyDVZC3Y4ES/u61Q7LDnB3kG9MnXJsJiQxm1pLkE7Zfxy29d5JaXbbfwhCDSjE4+dUQoq2MVIt2qVjZSo5Hd/bAFGU1Lmc7GkFeLiLjNTOfECF52ms/dks92Wx/glfRuK4h/fcxtGB4Q2VXu5k68e/2uojs6jnFsMKVe+FVUDkQIDAQAB
-----END PUBLIC KEY-----"""


def encrypt_pwd(plain: str) -> str:
    """RSA 加密密码，返回 URL-encoded base64 字符串"""
    rsa_key = RSA.importKey(RSA_PUB_KEY)
    cipher = PKCS1_v1_5.new(rsa_key)
    enc = cipher.encrypt(plain.encode('utf-8'))
    return urllib.parse.quote(base64.b64encode(enc).decode('utf-8'))

USERNAME_FULL = "63-9568348610"
COUNTRY_CODE  = "+63"
PHONE_NUMBER  = "9568348610"
PASSWORD      = "Zc627788***"

PROXY_SERVER = "http://127.0.0.1:10808"
CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'config')
os.makedirs(CONFIG_DIR, exist_ok=True)
SESSION_FILE = os.path.join(CONFIG_DIR, 'session.json')
MAX_CAPTCHA_RETRIES = 15


def _debug_screenshot(page, name):
    """保存调试截图"""
    path = os.path.join(CONFIG_DIR, f"debug_{name}.png")
    try:
        page.screenshot(path=path)
        print(f"  📸 截图: {path}")
    except Exception:
        pass


def solve_captcha(b64_data: str) -> str:
    if "," in b64_data:
        b64_data = b64_data.split(",", 1)[1]
    img_bytes = base64.b64decode(b64_data)
    ocr = ddddocr.DdddOcr(show_ad=False)
    return ocr.classification(img_bytes).strip()


def wait_for_form(page, timeout=20):
    """等待登录表单出现，每秒检查一次，超时返回 False"""
    print(f"  ⏳ 等待登录表单 (最多 {timeout}s)...")
    for i in range(timeout):
        try:
            page.wait_for_selector("input[name='username']", timeout=1000)
            page.wait_for_selector("img.captcha-img", timeout=1000)
            print(f"  ✅ 表单已加载 (耗时 {i+1}s)")
            return True
        except PlaywrightTimeout:
            if i % 5 == 4:
                print(f"    已等待 {i+1}s... 当前 URL: {page.url[:80]}")
            continue
    _debug_screenshot(page, "form_timeout")
    return False


def run_auto_login():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        context = browser.new_context(
            viewport={"width": 1536, "height": 960},
            proxy={"server": PROXY_SERVER} if PROXY_SERVER else None,
        )
        page = context.new_page()

        print("═" * 56)
        print("  裁判文书网 - 全自动登录 v2 (Playwright + OCR)")
        print("═" * 56)

        # =====================================================================
        # Step 1: 打开 wenshu，调 tongyiLogin/authorize 拿 OAuth URL
        # =====================================================================
        print("\n⏳ [1/4] 打开文书网 → 获取 OAuth 授权链接...")
        page.goto(WENSHU_LOGIN_URL :=
            "https://wenshu.court.gov.cn/website/wenshu/181010CARHS5BS3C/index.html?open=login",
            wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        oauth_url = page.evaluate("""
            async () => {
                const r = await fetch("https://wenshu.court.gov.cn/tongyiLogin/authorize", {
                    method:"POST",
                    headers:{
                        "accept":"*/*","x-requested-with":"XMLHttpRequest",
                        "referer":"https://wenshu.court.gov.cn/website/wenshu/181010CARHS5BS3C/index.html?open=login"
                    },
                    credentials:"omit"
                });
                return await r.text();
            }
        """).strip()

        if not oauth_url.startswith("http"):
            print(f"❌ OAuth URL 获取失败: {oauth_url[:100]}")
            _debug_screenshot(page, "oauth_fail")
            browser.close()
            sys.exit(1)
        print(f"  ✅ OAuth URL: {oauth_url[:80]}...")

        # =====================================================================
        # Step 2: 导航到 oauth/authorize（浏览器行为：会 302 跳到 account 页）
        # =====================================================================
        print("\n⏳ [2/4] 导航到 oauth/authorize（模拟浏览器 302 跳转到登录页）...")
        page.goto(oauth_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        print(f"  落地 URL: {page.url[:100]}...")

        # 检查是否在 account 登录页，如果不是等跳转
        if "account.court.gov.cn" not in page.url:
            print("  ⚠️ 未在 account 页面，等待跳转...")
            try:
                page.wait_for_url("**account.court.gov.cn/app**", timeout=15000)
                print(f"  ✅ 已跳转到: {page.url[:80]}...")
            except PlaywrightTimeout:
                print("  ⚠️ 跳转超时，尝试直接导航...")
                account_url = f"https://account.court.gov.cn/app?back_url={urllib.parse.quote(oauth_url, safe='')}#/login"
                page.goto(account_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)
                print(f"  当前 URL: {page.url[:80]}...")

        # =====================================================================
        # Step 3: 等待登录表单
        # =====================================================================
        if not wait_for_form(page, timeout=25):
            print("❌ 登录表单未出现，请检查网络/代理")
            _debug_screenshot(page, "no_form")
            browser.close()
            sys.exit(1)

        # --- 用 JS 直接设区号 +63（绕过 DOM 交互问题）---
        print(f"\n  设置国家代码 {COUNTRY_CODE} (JS 直设)...")
        page.evaluate(f"""
            () => {{
                // 直接改 hidden input 的值
                const codeInput = document.querySelector('input[name="phoneCode"]');
                if (codeInput) {{
                    codeInput.value = '{COUNTRY_CODE}';
                    // 更新显示的假 input
                    const fake = document.querySelector('.code-input-fake');
                    if (fake) fake.textContent = '{COUNTRY_CODE}';
                }}
            }}
        """)
        print(f"  ✅ 已设区号为 {COUNTRY_CODE}")

        # --- 填手机号 ---
        try:
            pi = page.wait_for_selector("input[name='username']", timeout=5000)
            pi.click(); pi.fill(""); pi.type(PHONE_NUMBER, delay=50)
            print(f"  ✅ 已填手机号: {PHONE_NUMBER}")
        except Exception as e:
            print(f"  ❌ 填手机号失败: {e}")

        # --- 填密码 ---
        try:
            pw = page.wait_for_selector("input[name='password']", timeout=5000)
            pw.click(); pw.fill(PASSWORD)
            print("  ✅ 已填密码")
        except Exception as e:
            print(f"  ❌ 填密码失败: {e}")

        # --- 清除所有前端校验错误（手机号格式等）---
        page.evaluate("""
            () => {
                // 隐藏所有校验错误消息
                document.querySelectorAll('.validator-error-msg').forEach(el => {
                    el.style.display = 'none';
                    el.textContent = '';
                });
                // 移除 has-error class
                document.querySelectorAll('.has-error').forEach(el => {
                    el.classList.remove('has-error');
                });
            }
        """)
        print("  ✅ 已清除前端校验错误")

        # =====================================================================
        # Step 4: 验证码识别 + 登录重试循环
        # =====================================================================
        # 预先 RSA 加密密码（每次登录都用同一个）
        encrypted_password = encrypt_pwd(PASSWORD)
        print(f"\n⏳ [3/4] 开始验证码识别 + 登录循环 (最多 {MAX_CAPTCHA_RETRIES} 次)...")
        login_ok = False

        for attempt in range(1, MAX_CAPTCHA_RETRIES + 1):
            print(f"\n  ── 第 {attempt}/{MAX_CAPTCHA_RETRIES} 次 ──")

            # 确认还在登录页
            if "account.court.gov.cn" not in page.url:
                print("  ⚠️ 页面已离开登录页，可能已登录成功？")
                if "wenshu.court.gov.cn/website/wenshu" in page.url:
                    login_ok = True
                break

            # 获取验证码
            try:
                page.wait_for_selector("img.captcha-img", timeout=8000)
            except PlaywrightTimeout:
                print("  ⚠️ 验证码图片未出现，刷新页面重试...")
                page.reload(wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                continue

            src = page.get_attribute("img.captcha-img", "src") or ""
            if not src.startswith("data:"):
                print("  ⚠️ 验证码 src 无效，点击刷新...")
                try:
                    page.click("img.captcha-img", force=True)
                except Exception:
                    pass
                page.wait_for_timeout(2000)
                src = page.get_attribute("img.captcha-img", "src") or ""

            # OCR
            try:
                ans = solve_captcha(src)
                print(f"  🔍 OCR → '{ans}'")
            except Exception as e:
                print(f"  ❌ OCR 异常: {e}")
                try:
                    page.click("img.captcha-img", force=True)
                except Exception:
                    pass
                page.wait_for_timeout(1500)
                continue

            if len(ans) < 2:
                print("  ⚠️ 识别太短，刷新验证码")
                try:
                    page.click("img.captcha-img", force=True)
                except Exception:
                    pass
                page.wait_for_timeout(1500)
                continue

            # 填入验证码
            try:
                ci = page.wait_for_selector("input[name='captcha']", timeout=3000)
                ci.click(); ci.fill(""); ci.type(ans, delay=30)
                print(f"  ✅ 已填入: {ans}")
            except Exception as e:
                print(f"  ⚠️ 填入验证码失败: {e}")

            # ---- 直接 JS fetch 发登录请求（绕过按钮和前端校验）----
            print("  🚀 直接调用 /api/login（绕过按钮和校验）...")
            login_result = page.evaluate("""
                async ([encPwd]) => {
                    // 读取表单里的 hidden token
                    const tokenEl = document.querySelector('input[name="token"]');
                    const bizTokenEl = document.querySelector('input[name="bizToken"]');
                    const imgTokenEl = document.querySelector('input[name="imgVerifyToken"]');
                    const phoneCodeEl = document.querySelector('input[name="phoneCode"]');
                    const usernameEl = document.querySelector('input[name="username"]');
                    const captchaEl = document.querySelector('input[name="captcha"]');

                    const token = tokenEl ? tokenEl.value : '';
                    const bizToken = bizTokenEl ? bizTokenEl.value : '';
                    const imgToken = imgTokenEl ? imgTokenEl.value : '';
                    const phoneCode = phoneCodeEl ? (phoneCodeEl.value || '').replace('+', '') : '63';
                    const username = usernameEl ? usernameEl.value : '';
                    const captcha = captchaEl ? captchaEl.value : '';

                    // 构造登录 body（与浏览器 fetch 完全一致）
                    const body = new URLSearchParams();
                    body.append('username', phoneCode + '-' + username);
                    body.append('password', encPwd);   // ← RSA 加密后的密码
                    body.append('bizToken', bizToken || imgToken);
                    body.append('imgVerifyToken', imgToken || bizToken);
                    body.append('appDomain', 'wenshu.court.gov.cn');

                    try {
                        const resp = await fetch('https://account.court.gov.cn/api/login', {
                            method: 'POST',
                            headers: {
                                'accept': '*/*',
                                'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                                'x-requested-with': 'XMLHttpRequest',
                                'referer': window.location.href
                            },
                            body: body.toString(),
                            credentials: 'include'
                        });
                        const data = await resp.json();
                        return JSON.stringify({success: data.success || data.code === '000000', data: data});
                    } catch(e) {
                        return JSON.stringify({success: false, error: e.message});
                    }
                }
            """, [encrypted_password])
            try:
                result = json.loads(login_result)
                print(f"  📡 API 返回: {json.dumps(result, ensure_ascii=False)[:150]}")
                if result.get("success"):
                    print("  🎉 /api/login 成功！正在执行 OAuth 回调...")
                    page.wait_for_timeout(1500)  # 等 HOLDONKEY cookie 落盘
                    # 直接用 page.goto 跳到 OAuth URL（完整跟踪 302 链，等 networkidle）
                    print(f"  🔀 跳转 OAuth: {oauth_url[:80]}...")
                    page.goto(oauth_url, wait_until="networkidle", timeout=60000)
                    page.wait_for_timeout(3000)
                    print(f"  落地 URL: {page.url[:100]}...")

                    # 检查最终是否在 wenshu 首页
                    for _ in range(6):  # 最多等 12 秒
                        try:
                            u = page.url
                            if "wenshu.court.gov.cn/website/wenshu" in u and \
                               "CallBackController" not in u and \
                               "account.court.gov.cn" not in u:
                                print("  🎉 登录成功！已在文书网首页")
                                login_ok = True
                                break
                        except Exception:
                            pass
                        page.wait_for_timeout(2000)

                    if login_ok:
                        break
                    else:
                        print(f"  ⚠️ OAuth 跳转后未到 wenshu 首页，当前 URL: {page.url[:80]}")
                        # 继续尝试：可能 CallBackController 页面需要再等一下
                        page.wait_for_timeout(3000)
                        if "wenshu.court.gov.cn/website/wenshu" in page.url:
                            login_ok = True
                            break
                else:
                    print(f"  ⚠️ 登录失败: {result.get('data', {}).get('message', '')}")
            except json.JSONDecodeError:
                print(f"  ⚠️ 无法解析 API 返回: {login_result[:100]}")

            # 等跳转
            page.wait_for_timeout(4000)

            # 检查成功
            try:
                u = page.url
                if "wenshu.court.gov.cn/website/wenshu" in u and \
                   "CallBackController" not in u:
                    print("  🎉 登录成功！")
                    login_ok = True
                    break
            except Exception:
                pass

            # 多等 3 秒
            if not login_ok:
                page.wait_for_timeout(3000)
                try:
                    u = page.url
                    if "wenshu.court.gov.cn/website/wenshu" in u and \
                       "CallBackController" not in u:
                        print("  🎉 登录成功！")
                        login_ok = True
                        break
                except Exception:
                    pass

            # 打印错误
            try:
                err = page.query_selector(
                    ".login-error-tips:not([style*='display: none'])")
                if err:
                    txt = (err.text_content() or "").strip()
                    if txt:
                        print(f"  ⚠️ 错误: {txt}")
            except Exception:
                pass

            # 刷新验证码
            try:
                page.click("img.captcha-img", force=True)
            except Exception:
                pass
            page.wait_for_timeout(2000)

        if not login_ok:
            print(f"\n❌ {MAX_CAPTCHA_RETRIES} 次均失败")
            _debug_screenshot(page, "all_failed")
            browser.close()
            sys.exit(1)

        # =====================================================================
        # Step 5: 拿 PAGE_ID + 提取 Cookie
        # =====================================================================
        print("\n⏳ [4/4] 提取凭据...")
        page.wait_for_timeout(3000)

        # 去搜索页拿 PAGE_ID
        SEARCH_URL = "https://wenshu.court.gov.cn/website/wenshu/181217BMTKHNT2W0/index.html"
        page.goto(SEARCH_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(5000)  # 等 JS 完全初始化

        page_id = None
        # 方式1: URL 参数
        m = re.search(r'pageId=([a-f0-9]{32})', page.url)
        if m:
            page_id = m.group(1)
        # 方式2: JS 全局变量
        if not page_id:
            for var in ["__pageId", "pageId", "_pageId", "window.pageId"]:
                try:
                    val = page.evaluate(f"() => window.{var} || ''")
                    if val and len(val) == 32:
                        page_id = val
                        break
                except Exception:
                    pass
        # 方式3: 从页面发一个 API 请求，从请求体里抓 pageId
        if not page_id:
            try:
                extracted = page.evaluate("""
                    async () => {
                        // 发一个 wsCountSearch 请求迫使页面生成 pageId
                        const resp = await fetch('/website/parse/rest.q4w', {
                            method: 'POST',
                            headers: {
                                'accept': 'application/json, text/javascript, */*; q=0.01',
                                'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                                'x-requested-with': 'XMLHttpRequest'
                            },
                            body: 'cfg=com.lawyee.judge.dc.parse.dto.SearchDataDsoDTO%40wsCountSearch&__RequestVerificationToken=test&wh=960&ww=1531&cs=0',
                            credentials: 'include'
                        });
                        await resp.json();
                        // 再尝试从全局拿
                        return window.__pageId || window.pageId || '';
                    }
                """)
                if extracted and len(extracted) == 32:
                    page_id = extracted
            except Exception:
                pass
        # 方式4: 从页面 HTML 源码找
        if not page_id:
            m = re.search(r'(?:pageId|__pageId)["\']?\s*[:=]\s*["\']([a-f0-9]{32})["\']', page.content())
            if m:
                page_id = m.group(1)

        cookies = context.cookies()
        sess_val = holdon_val = None
        for c in cookies:
            d, n, v = c.get("domain", ""), c["name"], c["value"]
            if n == "SESSION" and "wenshu" in d:
                sess_val = v
            if n == "HOLDONKEY" and "account" in d:
                holdon_val = v

        print(f"  PAGE_ID:   {page_id or '❌'}")
        print(f"  SESSION:   {sess_val or '❌'}")
        print(f"  HOLDONKEY: {holdon_val or '❌'}")

        if not sess_val:
            print("❌ 无 SESSION")
            browser.close()
            sys.exit(1)

        # 保存所有 cookie（不仅是 SESSION + HOLDONKEY）
        all_cookies = {}
        for c in cookies:
            all_cookies[c["name"]] = {
                "value": c["value"],
                "domain": c.get("domain", ""),
            }
        # 用浏览器自己的 fetch 验证 SESSION 是否真的已认证
        print("\n🔍 浏览器内验证 SESSION...")
        browser_check = page.evaluate("""
            async () => {
                const r = await fetch('/website/parse/rest.q4w', {
                    method: 'POST',
                    headers: {
                        'accept': 'application/json, text/javascript, */*; q=0.01',
                        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                        'x-requested-with': 'XMLHttpRequest'
                    },
                    body: 'cfg=com.lawyee.wbsttools.web.parse.dto.AppUserDTO%40currentUser',
                    credentials: 'include'
                });
                const j = await r.json();
                return JSON.stringify(j);
            }
        """)
        try:
            bc = json.loads(browser_check)
            u = bc.get("result", {})
            nm = u.get("userName") or u.get("realName") or u.get("userId") or ""
            if "anonymous" in str(nm).lower() or not nm:
                print(f"  ❌ 浏览器内也是匿名！SESSION 确实未认证。响应: {browser_check[:200]}")
            else:
                print(f"  ✅ 浏览器内验证通过: {nm}")
        except Exception:
            print(f"  ⚠️ 浏览器验证异常: {browser_check[:100]}")

        # 再用 curl_cffi 验证（对比）
        print("🔍 curl_cffi 验证 SESSION...")
        try:
            from curl_cffi import requests as cr
            s2 = cr.Session()
            s2.cookies.set("SESSION", sess_val, domain="wenshu.court.gov.cn")
            r2 = s2.post(
                "https://wenshu.court.gov.cn/website/parse/rest.q4w",
                headers={
                    "accept": "application/json, text/javascript, */*; q=0.01",
                    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "referer": "https://wenshu.court.gov.cn/website/wenshu/181217BMTKHNT2W0/index.html",
                    "x-requested-with": "XMLHttpRequest",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
                data={"cfg": "com.lawyee.wbsttools.web.parse.dto.AppUserDTO@currentUser"},
                proxies={"http": PROXY_SERVER, "https": PROXY_SERVER},
                timeout=15, impersonate="chrome120"
            )
            u2 = r2.json().get("result", {})
            nm2 = u2.get("userName") or u2.get("realName") or u2.get("userId") or ""
            if "anonymous" in str(nm2).lower() or not nm2:
                print(f"  ❌ curl_cffi 也是匿名: {r2.text[:150]}")
            else:
                print(f"  ✅ curl_cffi 验证通过: {nm2}")
        except Exception as e:
            print(f"  ❌ curl_cffi 异常: {e}")

        json.dump({
            "username": USERNAME_FULL,
            "page_id": page_id,
            "session": sess_val,
            "holdonkey": holdon_val,
            "nccookie": all_cookies.get("ncCookie", {}).get("value", ""),
            "wzws_reurl": all_cookies.get("wzws_reurl", {}).get("value", ""),
            "bl_uid": all_cookies.get("_bl_uid", {}).get("value", ""),
            "all_cookies": all_cookies,
            "timestamp": int(time.time()),
        }, open(SESSION_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        print(f"\n💾 已保存: {SESSION_FILE}")

        # =====================================================================
        # 浏览器保持打开，等用户手动操作；全程录制请求
        # =====================================================================
        print("\n" + "═" * 56)
        print("  🔓 登录已完成，浏览器保持打开")
        print("═" * 56)
        print()
        print("  📌 你现在可以手动操作：")
        print("    1. 打开搜索页获取 PAGE_ID")
        print("    2. 做几次搜索，观察请求里的 SESSION")
        print("    3. 对比存储的 SESSION 是否与请求一致")
        print()
        print("  📡 脚本将持续录制 API 请求...")
        print("  🛑 操作完后直接关闭浏览器窗口即可")
        print()

        captured = []
        def _on_req(request):
            url = request.url
            if any(k in url for k in ["rest.q4w", "tongyiLogin", "captcha",
                                        "api/login", "oauth", "CallBackController"]):
                captured.append({
                    "type": "request",
                    "url": url,
                    "method": request.method,
                    "headers": dict(request.headers),
                    "postData": request.post_data,
                })
        def _on_resp(response):
            url = response.url
            if any(k in url for k in ["rest.q4w", "tongyiLogin", "captcha",
                                        "api/login", "oauth", "CallBackController"]):
                try:
                    body = response.text()[:1500]
                except Exception:
                    body = "(binary)"
                captured.append({
                    "type": "response",
                    "url": url,
                    "status": response.status,
                    "headers": dict(response.headers),
                    "body": body,
                })
        page.on("request", _on_req)
        page.on("response", _on_resp)

        try:
            page.wait_for_event("close", timeout=600000)
        except PlaywrightTimeout:
            print("\n⏰ 10 分钟超时，自动关闭...")
        except Exception:
            pass

        req_file = os.path.join(CONFIG_DIR, "manual_requests.json")
        with open(req_file, "w", encoding="utf-8") as f:
            json.dump(captured, f, indent=2, ensure_ascii=False)
        print(f"\n📁 录制了 {len(captured)} 条请求 → {req_file}")

        print("\n🔍 SESSION 对比:")
        print(f"  存储的:  {sess_val}")
        for req in captured:
            if req["type"] == "request":
                for hk, hv in req.get("headers", {}).items():
                    if hk.lower() == "cookie" and "SESSION=" in hv:
                        m = re.search(r'SESSION=([^;]+)', hv)
                        if m:
                            ms = m.group(1)
                            tag = "✅ 一致" if ms == sess_val else "❌ 不同!"
                            print(f"  请求中:  {ms} {tag}")

        browser.close()


if __name__ == "__main__":
    run_auto_login()
