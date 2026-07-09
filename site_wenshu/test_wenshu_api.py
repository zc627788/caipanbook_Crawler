import requests
import json
import time
import urllib.parse
from datetime import datetime
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))
from utils.wenshu_crypto import generate_random_salt, encrypt_ciphertext, decrypt_result

SESSION_COOKIE   = "c6093a61-7609-49a1-921a-e46d022f2fdf"
HOLDONKEY_COOKIE = "NGY4YzgzNTEtNmI4ZC00YmQ4LTgyNzMtYWRkZDYwNWY3Mjkx"
PAGE_ID    = "98007c56b09161187d3a0a6fe0515b25"
PROXIES = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}

def make_session():
    sess = requests.Session()
    sess.cookies.set("SESSION", SESSION_COOKIE, domain="wenshu.court.gov.cn")
    sess.cookies.set("HOLDONKEY", HOLDONKEY_COOKIE, domain="account.court.gov.cn")
    return sess

def call_api(sess, body_str):
    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    cipher = encrypt_ciphertext(int(time.time() * 1000), generate_random_salt(24), date_str)
    token = generate_random_salt(24)

    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "sec-ch-ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "x-requested-with": "XMLHttpRequest",
        "referer": f"https://wenshu.court.gov.cn/website/wenshu/181217BMTKHNT2W0/index.html?pageId={PAGE_ID}",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    }
    
    body = body_str + f"&ciphertext={urllib.parse.quote(cipher)}&__RequestVerificationToken={token}"

    try:
        resp = sess.post(
            "https://wenshu.court.gov.cn/website/parse/rest.q4w",
            headers=headers, data=body, proxies=PROXIES, timeout=20
        )
        j = resp.json()
        if j.get("code") == 1:
            try:
                dec = decrypt_result(j["result"], j["secretKey"], date_str)
                return json.loads(dec)
            except Exception as e:
                return {"error_decrypt": str(e), "raw": j}
        return j
    except Exception as e:
        return {"error": str(e)}

def main():
    sess = make_session()
    
    print("--- Test A: leftDataItem for a day ---")
    cond_a = [{"key":"cprq","value":"2015-06-03 TO 2015-06-03"}]
    cond_a_str = urllib.parse.quote(json.dumps(cond_a, separators=(',', ':')))
    body_a = f"pageId={PAGE_ID}&cprqStart=2015-06-03&queryCondition={cond_a_str}&groupFields=s45%3Bs11%3Bs4%3Bs33%3Bs42%3Bs8%3Bs6%3Bs44&cfg=com.lawyee.judge.dc.parse.dto.SearchDataDsoDTO%40leftDataItem&wh=1279&ww=2560&cs=0"
    res_a = call_api(sess, body_a)
    if isinstance(res_a, dict) and 's33' in res_a:
        print("s33 counts:", [x for x in res_a['s33']][:3])
    else:
        print(res_a)
        
    print("\n--- Test B: leftDataItem for Beijing ---")
    cond_b = [{"key":"cprq","value":"2015-06-03 TO 2015-06-03"}, {"key":"s33","value":"北京市"}]
    cond_b_str = urllib.parse.quote(json.dumps(cond_b, separators=(',', ':')))
    body_b = f"pageId={PAGE_ID}&cprqStart=2015-06-03&queryCondition={cond_b_str}&groupFields=s39%2Cs40&facetLimit=1000&cfg=com.lawyee.judge.dc.parse.dto.SearchDataDsoDTO%40leftDataItem&wh=1279&ww=2560&cs=0"
    res_b = call_api(sess, body_b)
    if isinstance(res_b, dict):
        print("s39 counts:", res_b.get('s39', [])[:3])
        print("s40 counts:", res_b.get('s40', [])[:3])
    else:
        print(res_b)
        
    print("\n--- Test C: loadFyByCode (110 = Beijing) ---")
    body_c = f"pageId={PAGE_ID}&cprqStart=2015-06-03&parentCode=110&cfg=com.lawyee.judge.dc.parse.dto.LoadDicDsoDTO%40loadFyByCode&wh=1279&ww=2560&cs=0"
    res_c = call_api(sess, body_c)
    if isinstance(res_c, list):
        print("Courts:", res_c[:3])
    else:
        print("Courts:", res_c)
    
    print("\n--- Test D: loadFyByCode (100 = Top level) ---")
    body_d = f"pageId={PAGE_ID}&cprqStart=2015-06-03&parentCode=100&cfg=com.lawyee.judge.dc.parse.dto.LoadDicDsoDTO%40loadFyByCode&wh=1279&ww=2560&cs=0"
    res_d = call_api(sess, body_d)
    print("\n--- Test E: queryDoc (Check if cookie is still valid) ---")
    query_doc_cond = urllib.parse.quote(json.dumps([{"key":"cprq","value":"2015-06-03 TO 2015-06-03"}], separators=(',', ':')))
    body_e = f"pageId={PAGE_ID}&cprqStart=2015-06-03&cprqEnd=2015-06-03&sortFields=s50%3Adesc&pageNum=1&pageSize=5&queryCondition={query_doc_cond}&cfg=com.lawyee.judge.dc.parse.dto.SearchDataDsoDTO%40queryDoc&wh=1279&ww=2560&cs=0"
    res_e = call_api(sess, body_e)
    if isinstance(res_e, dict) and "queryResult" in res_e:
        print("queryDoc works! Count:", res_e["queryResult"].get("resultCount"))
    else:
        print("queryDoc failed:", res_e)
        
if __name__ == "__main__":
    main()
