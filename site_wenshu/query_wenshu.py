import os
import json
import time
import requests
from datetime import datetime
from utils.wenshu_crypto import generate_random_salt, encrypt_ciphertext, decrypt_result

# 代理配置
PROXIES = {
    'http': 'http://127.0.0.1:10808',
    'https': 'http://127.0.0.1:10808'
}

SESSION_FILE = os.path.join(os.path.dirname(__file__), 'config', 'session.json')

# ============================================================
# 可手动覆盖 Cookie（浏览器手动登录后 F12 → Application → Cookies）
# 留空则自动从 session.json 读取
# ============================================================
MANUAL_SESSION_COOKIE = "73cf86ca-a6f7-43f1-b0a6-641c95c71be6"
MANUAL_HOLDONKEY_COOKIE = "YzFhYjcyMjctMTc3Zi00MjEzLThiNTctZDg3MzBhOTM1ODRl"
# ============================================================

def build_session():
    """构建已认证的 requests.Session"""
    sess = requests.Session()

    if MANUAL_SESSION_COOKIE:
        sess.cookies.set("SESSION", MANUAL_SESSION_COOKIE, domain="wenshu.court.gov.cn")
        if MANUAL_HOLDONKEY_COOKIE:
            sess.cookies.set("HOLDONKEY", MANUAL_HOLDONKEY_COOKIE, domain="account.court.gov.cn")
        print(f"[*] 使用手动指定 Cookie (SESSION={MANUAL_SESSION_COOKIE[:16]}...)")
        return sess

    if not os.path.exists(SESSION_FILE):
        raise FileNotFoundError(f"找不到会话文件: {SESSION_FILE}，请先运行 login_alipay_qr.py 登录。")

    with open(SESSION_FILE, 'r', encoding='utf-8') as f:
        session_data = json.load(f)

    cookies = session_data.get("cookies", {})
    sess.cookies.update(cookies)
    print(f"[*] 已载入会话 Cookie (SESSION={cookies.get('SESSION', '?')[:16]}...)")
    return sess


def query_wenshu_documents(keyword=None, cprq_start=None, cprq_end=None, page_num=1, page_size=5):
    """
    搜索裁判文书。支持关键词搜索或裁判日期范围搜索。
    keyword: 搜索关键词（如 "裁判文书"），对应 s21 字段
    cprq_start/cprq_end: 裁判日期范围（如 "2025-07-01"）
    """
    sess = build_session()

    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    timestamp_ms = int(time.time() * 1000)
    salt = generate_random_salt(24)
    ciphertext = encrypt_ciphertext(timestamp_ms, salt, date_str)
    token = generate_random_salt(24)

    # 构建 queryCondition
    query_condition = []
    if keyword:
        query_condition.append({"key": "s21", "value": keyword})
    if cprq_start and cprq_end:
        query_condition.append({"key": "cprq", "value": f"{cprq_start} TO {cprq_end}"})
    if not query_condition:
        query_condition = [{"key": "cprq", "value": "2025-07-01 TO 2025-07-31"}]

    # pageId 和 referer 与浏览器请求完全匹配（带日期参数的那个请求）
    PAGE_ID = "a9b96816dedd13378a5860906247c7d5"
    referer_url = f"https://wenshu.court.gov.cn/website/wenshu/181217BMTKHNT2W0/index.html?pageId={PAGE_ID}"
    if cprq_start:
        referer_url += f"&cprqStart={cprq_start}"
    if cprq_end:
        referer_url += f"&cprqEnd={cprq_end}"
    if keyword:
        import urllib.parse
        referer_url += f"&s21={urllib.parse.quote(keyword)}"

    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "cache-control": "no-cache",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "pragma": "no-cache",
        "sec-ch-ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "x-requested-with": "XMLHttpRequest",
        "referer": referer_url,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
    }

    url = "https://wenshu.court.gov.cn/website/parse/rest.q4w"

    # 构建 POST body（与浏览器完全一致的字段集合）
    post_data = {
        "pageId": PAGE_ID,
        "sortFields": "s50:desc",
        "ciphertext": ciphertext,
        "pageNum": str(page_num),
        "pageSize": str(page_size),
        "queryCondition": json.dumps(query_condition, separators=(',', ':')),
        "cfg": "com.lawyee.judge.dc.parse.dto.SearchDataDsoDTO@queryDoc",
        "__RequestVerificationToken": token,
        "wh": "791",
        "ww": "1536",
        "cs": "0"
    }
    # 裁判日期范围参数必须也作为独立字段传入（浏览器请求里同时在 body 和 queryCondition 里都有）
    if keyword:
        post_data["s21"] = keyword
    if cprq_start:
        post_data["cprqStart"] = cprq_start
    if cprq_end:
        post_data["cprqEnd"] = cprq_end

    print(f"[*] 发起搜索请求... queryCondition={json.dumps(query_condition, ensure_ascii=False)}")
    resp = sess.post(url, headers=headers, data=post_data, proxies=PROXIES, timeout=15)
    print(f"[+] 响应状态码: {resp.status_code}")

    if resp.status_code != 200:
        print(f"❌ HTTP 错误: {resp.text[:300]}")
        return

    resp_json = resp.json()
    code = resp_json.get("code")

    if code != 1:
        print(f"❌ 接口返回 code={code}, 描述: {resp_json.get('description')}")
        if code == 9:
            print("   ↳ Code 9 表示未登录或 SESSION 已过期，请重新登录获取 Cookie！")
        return

    secret_key = resp_json.get("secretKey")
    result_encrypted = resp_json.get("result")
    print(f"[+] 成功获取解密密钥，正在本地解密...")

    decrypted_text = decrypt_result(result_encrypted, secret_key, date_str)
    decrypted_json = json.loads(decrypted_text)

    print("\n" + "═" * 30 + " 解密数据成功 " + "═" * 30)
    query_result = decrypted_json.get("queryResult", {})
    result_count = query_result.get("resultCount", 0)
    result_list = query_result.get("resultList", [])

    print(f"📊 查询结果总数: {result_count}")
    print(f"📑 本页返回条数: {len(result_list)}\n")

    for idx, doc in enumerate(result_list):
        title = doc.get("1", "无标题")
        court = doc.get("2", "无法院")
        case_no = doc.get("7", "无案号")
        date_pub = doc.get("31", "无日期")

        print(f"【文书 #{idx+1}】")
        print(f"  ▪ 标题: {title}")
        print(f"  ▪ 案号: {case_no}")
        print(f"  ▪ 法院: {court}")
        print(f"  ▪ 发布日期: {date_pub}")
        print("─" * 74)

    return decrypted_json


if __name__ == "__main__":
    import requests, time, json, sys, os, urllib.parse
    from datetime import datetime
    sys.path.insert(0, os.path.dirname(__file__))
    from utils.wenshu_crypto import generate_random_salt, encrypt_ciphertext, decrypt_result

    sess = requests.Session()
    sess.cookies.set("SESSION", MANUAL_SESSION_COOKIE, domain="wenshu.court.gov.cn")
    sess.cookies.set("HOLDONKEY", MANUAL_HOLDONKEY_COOKIE, domain="account.court.gov.cn")

    PROXIES = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}
    now = datetime.now()
    date_str = now.strftime("%Y%m%d")

    # 浏览器里带有效日期过滤的 pageId（服务端有状态，此 pageId 直接对应 647801 条结果）
    PAGE_ID = "a9b96816dedd13378a5860906247c7d5"

    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "cache-control": "no-cache",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "pragma": "no-cache",
        "sec-ch-ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "x-requested-with": "XMLHttpRequest",
        "referer": f"https://wenshu.court.gov.cn/website/wenshu/181217BMTKHNT2W0/index.html?pageId={PAGE_ID}&cprqStart=2025-07-01&cprqEnd=2025-07-31",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    }

    def fetch_page(page_num, page_size):
        ciphertext = encrypt_ciphertext(int(time.time()*1000), generate_random_salt(24), date_str)
        token = generate_random_salt(24)
        body = (
            f"pageId={PAGE_ID}"
            f"&cprqStart=2025-07-01"
            f"&cprqEnd=2025-07-31"
            f"&sortFields=s50%3Adesc"
            f"&ciphertext={urllib.parse.quote(ciphertext)}"
            f"&pageNum={page_num}"
            f"&pageSize={page_size}"
            f"&queryCondition=%5B%7B%22key%22%3A%22cprq%22%2C%22value%22%3A%222025-07-01+TO+2025-07-31%22%7D%5D"
            f"&cfg=com.lawyee.judge.dc.parse.dto.SearchDataDsoDTO%40queryDoc"
            f"&__RequestVerificationToken={token}"
            f"&wh=791&ww=1536&cs=0"
        )
        r = sess.post("https://wenshu.court.gov.cn/website/parse/rest.q4w",
                      headers=headers, data=body, proxies=PROXIES, timeout=15)
        j = r.json()
        if j.get("code") == 1:
            dec = decrypt_result(j["result"], j["secretKey"], date_str)
            return json.loads(dec)
        else:
            print(f"  ❌ code={j.get('code')}, desc={j.get('description')}")
            return None

    # 先测试第 1 页，10 条，确认过滤生效
    print("=== 第 1 页 10 条（验证日期过滤）===")
    result = fetch_page(1, 10)
    if result:
        qr = result.get("queryResult", {})
        print(f"总条数: {qr.get('resultCount')}")
        for i, doc in enumerate(qr.get("resultList", [])):
            print(f"  [{i+1}] {doc.get('31','?')} | {doc.get('1','?')[:50]}")

    # 测试大 page_size 能否突破 600 条限制
    print("\n=== 测试 page_size=20 ===")
    time.sleep(2)  # 风控间隔
    result2 = fetch_page(1, 20)
    if result2:
        qr2 = result2.get("queryResult", {})
        cnt = len(qr2.get("resultList", []))
        print(f"总条数: {qr2.get('resultCount')}, 本页实际返回: {cnt} 条")

    from utils.wenshu_crypto import generate_random_salt, encrypt_ciphertext, decrypt_result

    sess = requests.Session()
    sess.cookies.set("SESSION", MANUAL_SESSION_COOKIE, domain="wenshu.court.gov.cn")
    sess.cookies.set("HOLDONKEY", MANUAL_HOLDONKEY_COOKIE, domain="account.court.gov.cn")

    PROXIES = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}
    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    ciphertext = encrypt_ciphertext(int(time.time()*1000), generate_random_salt(24), date_str)
    token = generate_random_salt(24)

    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "cache-control": "no-cache",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "pragma": "no-cache",
        "sec-ch-ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "x-requested-with": "XMLHttpRequest",
        "referer": "https://wenshu.court.gov.cn/website/wenshu/181217BMTKHNT2W0/index.html?pageId=a9b96816dedd13378a5860906247c7d5&cprqStart=2025-07-01&cprqEnd=2025-07-31",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    }

    # 精确复刻浏览器 body，只替换 ciphertext 和 token
    import urllib.parse
    body = (
        f"pageId=a9b96816dedd13378a5860906247c7d5"
        f"&cprqStart=2025-07-01"
        f"&cprqEnd=2025-07-31"
        f"&sortFields=s50%3Adesc"
        f"&ciphertext={urllib.parse.quote(ciphertext)}"
        f"&pageNum=1"
        f"&pageSize=10"
        f"&queryCondition=%5B%7B%22key%22%3A%22cprq%22%2C%22value%22%3A%222025-07-01+TO+2025-07-31%22%7D%5D"
        f"&cfg=com.lawyee.judge.dc.parse.dto.SearchDataDsoDTO%40queryDoc"
        f"&__RequestVerificationToken={token}"
        f"&wh=791&ww=1536&cs=0"
    )

    r = sess.post("https://wenshu.court.gov.cn/website/parse/rest.q4w",
                  headers=headers, data=body, proxies=PROXIES, timeout=15)
    print(f"Status: {r.status_code}")
    j = r.json()
    print(f"code: {j.get('code')}")
    if j.get("code") == 1:
        dec = decrypt_result(j["result"], j["secretKey"], date_str)
        parsed = json.loads(dec)
        qr = parsed.get("queryResult", {})
        print(f"✅ 总条数: {qr.get('resultCount')}")
        for i, doc in enumerate(qr.get("resultList", [])):
            print(f"  [{i+1}] {doc.get('31','?')} | {doc.get('1','?')[:40]}")
    else:
        print(f"❌ {j}")

