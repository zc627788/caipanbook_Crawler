#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
裁判文书网 - 支付宝扫码登录纯协议全自动对接工具
依据 SKILL.md 规范：采用纯 HTTP 协议抓包拆解，脱离浏览器自动化
包含：OAuth 2.0 授权跳转 -> 扫码轮询 -> 自动换取文书网 Cookie -> 持久化会话
"""

import json
import os
import sys
import time
import requests

# 配置代理（按照工作区规范，默认走本地 10808 代理）
PROXIES = {
    'http': 'http://127.0.0.1:10808',
    'https': 'http://127.0.0.1:10808'
}

CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'config')
os.makedirs(CONFIG_DIR, exist_ok=True)
SESSION_FILE = os.path.join(CONFIG_DIR, 'session.json')
QR_IMAGE_FILE = os.path.join(os.path.dirname(__file__), 'alipay_qr.png')

def init_oauth(session):
    """
    第一步：调用文书网统一登录接口，获取 OAuth 授权跳转链接
    然后【关键】：用全新 session 访问 oauth_url，让 account.court.gov.cn
    在 OAuth 上下文中创建一个新的 HOLDONKEY 并重定向到登录页。
    这样后续 QR 扫码完成后，这个 HOLDONKEY 会被正确绑定到真实用户。
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
    print("⏳ [1/5] 正在初始化文书网 OAuth 鉴权链路...")
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
    
    # 【关键修正】不直接访问 oauth/authorize！
    # 浏览器的真实行为：访问 account.court.gov.cn/app?back_url=<encoded_oauth_url>
    # 由前端 JS 读取 back_url 并在扫码成功后跳转，服务端 state 不会被提前消耗
    # 如果直接访问 oauth/authorize，服务端会标记该 state 为「待认证」，
    # 但对 Python 来说后续再次访问时 state 依然无法通过认证，因为 account 端没有看到 JS 触发的授权
    print("⏳ [2/5] 正在访问 account 登录上下文页面（模仿浏览器行为）...")
    import urllib.parse
    app_url = f"https://account.court.gov.cn/app?back_url={urllib.parse.quote(oauth_url, safe='')}"
    login_page_headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "referer": "https://wenshu.court.gov.cn/"
    }
    login_resp = session.get(app_url, headers=login_page_headers, proxies=PROXIES,
                             allow_redirects=True, timeout=15)
    holdonkey = session.cookies.get('HOLDONKEY', domain='account.court.gov.cn')
    if holdonkey:
        print(f"✅ account 登录上下文已初始化！HOLDONKEY: {holdonkey[:16]}...")
        print(f"   登录页最终 URL: {login_resp.url[:80]}")
    else:
        print("⚠️ 未获取到 HOLDONKEY，account 登录上下文初始化可能失败")
        print(f"   当前 cookies: {session.cookies.get_dict()}")
    
    return oauth_url

def get_qr_code(session):
    """
    第二步：获取支付宝扫码登录二维码
    """
    url = "https://account.court.gov.cn/api/third/alipay/mini/getAlipayAppletQrCode"
    headers = {
        "accept": "*/*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "sec-ch-ua": "\"Google Chrome\";v=\"149\", \"Chromium\";v=\"149\", \"Not)A;Brand\";v=\"24\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "x-requested-with": "XMLHttpRequest",
        "referer": "https://account.court.gov.cn/app"
    }
    # 必须使用 type=reg 的二维码（即 pages/getPhoneNumber/getPhoneNumber），这样扫码后服务端会直接绑定 Session，不需要再调用 authLogin！
    data = "appId=2019110468943166&url=pages%2FgetPhoneNumber%2FgetPhoneNumber&queryParams=appId%3D2019110468943166&type=reg&appDomain=wenshu.court.gov.cn"
    
    print("⏳ [2/4] 正在向统一认证中心发包申请【支付宝登录二维码】...")
    resp = session.post(url, headers=headers, data=data, proxies=PROXIES, timeout=10)
    res_json = resp.json()
    
    if res_json.get("success") and res_json.get("code") == "000000":
        qr_data = res_json["data"]
        qr_url = qr_data["url"]
        uuid = qr_data["uuid"]
        print(f"✅ 成功提取二维码 UUID: {uuid}")
        print(f"🔗 二维码图片链接: {qr_url}")
        
        # 下载保存二维码图片到本地
        try:
            img_resp = session.get(qr_url, proxies=PROXIES, timeout=10)
            with open(QR_IMAGE_FILE, "wb") as f:
                f.write(img_resp.content)
            print(f"🖼️ 二维码图片已实时保存至: {QR_IMAGE_FILE}")
            print("💡 请掏出手机打开【支付宝】，扫一扫登录！")
        except Exception as e:
            print(f"⚠️ 保存二维码图片失败: {e}")
            
        return uuid, qr_url
    else:
        print("❌ 获取二维码失败:", res_json)
        sys.exit(1)

def poll_and_exchange(session, uuid, oauth_url):
    """
    第三步与第四步：轮询扫码状态 -> 成功后用已认证的 HOLDONKEY 重新访问 OAuth 链接
    此时 account 服务器看到已认证用户，颁发真实用户 code -> CallBackController 设置正式 SESSION
    """
    url_phone = f"https://account.court.gov.cn/api/third/alipay/pc/pollPhone?uuid={uuid}&appDomain=wenshu.court.gov.cn"
    url_result = f"https://account.court.gov.cn/api/third/alipay/mini/pollResult?uuid={uuid}&appDomain=wenshu.court.gov.cn"
    
    headers = {
        "accept": "*/*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "sec-ch-ua": "\"Google Chrome\";v=\"149\", \"Chromium\";v=\"149\", \"Not)A;Brand\";v=\"24\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "x-requested-with": "XMLHttpRequest",
        "referer": "https://account.court.gov.cn/app"
    }
    
    print("\n⏳ [3/4] 开始监听支付宝扫码确认状态（超时时间 3 分钟）...")
    start_time = time.time()
    
    while time.time() - start_time < 180:
        try:
            resp1 = session.get(url_phone, headers=headers, proxies=PROXIES, timeout=5)
            data1 = resp1.json()
            resp2 = session.get(url_result, headers=headers, proxies=PROXIES, timeout=5)
            data2 = resp2.json()
            
            code1 = data1.get("data", {}).get("code")
            code2 = data2.get("data", {}).get("code")
            
            if code1 != "0" or code2 != "0":
                print(f"\n🎉 [4/4] 捕捉到扫码确认成功！服务端状态已更变！")
                mobile = data1.get("data", {}).get("mobile") or data2.get("data", {}).get("mobile")
                print("\n🚀 [5/5] 正在用已认证 HOLDONKEY 访问新 OAuth 链接，获取真实用户 code...")
                # account 服务器此时看到 HOLDONKEY 是已认证的，且 Referer 完全匹配，会颁发真实用户的 code
                # CallBackController 拿到真实 code -> 拿到真实用户信息 -> 设置文书网认证 SESSION
                import urllib.parse
                exact_referer = f"https://account.court.gov.cn/app?back_url={urllib.parse.quote(oauth_url, safe='')}"
                exchange_headers = {
                    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "upgrade-insecure-requests": "1",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
                    "referer": exact_referer
                }
                holdonkey_val = session.cookies.get('HOLDONKEY', domain='account.court.gov.cn')
                print(f"  当前 HOLDONKEY: {holdonkey_val[:16] if holdonkey_val else '(空)'}...")
                cb_resp = session.get(oauth_url, headers=exchange_headers, proxies=PROXIES, allow_redirects=True, timeout=15)
                

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
                
                print(f"🍪 当前 session 中所有 Cookie（exchange 后）:")
                for c in session.cookies:
                    print(f"  域名={c.domain} | {c.name}={c.value}")
                
                # 核心关键：访问 window.open 跳转的落地页，触发服务端安全拦截器绑定 User 到 Session
                import re
                landing_match = re.search(r"window\.open\s*\(\s*['\"]([^'\"]+)['\"]", cb_resp.text)
                # 同时支持 location.href 跳转
                loc_match = re.search(r"(?:location\.href|window\.location)\s*=\s*['\"]([^'\"]+)['\"]", cb_resp.text)
                landing_url = cb_resp.url
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
                for c in session.cookies:
                    print(f"  域名={c.domain} | {c.name}={c.value}")
                
                # 立即验证：检查当前 session 是否已认证（同一 session 对象，不读文件）
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
                    user_id = chk_json.get("result", {}).get("userId", "(未获取到)") if isinstance(chk_json.get("result"), dict) else chk_json.get("result", "(未获取到)")
                    print(f"  ✅ currentUser 响应: {chk_json}")
                    if "anonymous" in str(user_id).lower():
                        print("  ❌ 警告: userId 仍为 anonymousUser，Session 未绑定用户！")
                    else:
                        print(f"  🎉 登录验证通过! userId = {user_id}")
                except:
                    print(f"  currentUser 原始响应: {chk_resp.text[:200]}")
                
                print(f"🍰 成功获取当前会话所有 Cookie！")
                
                # 只保留 wenshu 域及父域下的 Cookie，防止与 account.court.gov.cn 产生冲突
                final_cookies = {}
                for cookie in session.cookies:
                    print(f"  [Cookie Debug] {cookie.domain} -> {cookie.name}: {cookie.value}")
                    if "wenshu" in cookie.domain or cookie.domain == ".court.gov.cn":
                        final_cookies[cookie.name] = cookie.value
                
                session_data = {
                    "mobile": mobile,
                    "cookies": final_cookies,
                    "timestamp": int(time.time()),
                    "oauth_url": oauth_url,
                    "final_url": cb_resp.url,
                    "landing_url": landing_url
                }
                
                with open(SESSION_FILE, "w", encoding="utf-8") as f:
                    json.dump(session_data, f, indent=2, ensure_ascii=False)
                print(f"\n💾 文书网正式登录 Cookie 已持久化保存至: {SESSION_FILE}")
                print("═" * 54)
                print("📋 当前抓取到的文书网核心 Cookie 列表：")
                for k, v in final_cookies.items():
                    print(f"  ▪ {k}: {v}")
                print("═" * 54)
                
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
                
                print("💡 恭喜！您现在可以随时使用 session.json 中的 Cookie 调取 rest.q4w 检索文书数据了！")
                return session_data
            else:
                print(".", end="", flush=True)
                time.sleep(2)
        except KeyboardInterrupt:
            print("\n⏹️ 用户手动停止轮询。")
            break
        except Exception as e:
            print(f"\n⚠️ 轮询网络请求异常: {e}")
            time.sleep(2)
            
    print("\n⏰ 扫码超时，请重新运行脚本获取新二维码。")
    return None

if __name__ == "__main__":
    print("═" * 54)
    print("  中国裁判文书网 - 纯协议支付宝扫码全自动登录工具")
    print("═" * 54)
    
    with requests.Session() as s:
        oauth_url = init_oauth(s)
        uuid, qr_url = get_qr_code(s)
        poll_and_exchange(s, uuid, oauth_url)
