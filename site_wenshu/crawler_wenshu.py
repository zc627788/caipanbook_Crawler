"""
裁判文书网 2025-07 批量爬虫 v2.0 (自适应递归法院树遍历版)
- 断点续爬：支持精确到 [日期::省份::法院]
- 风控：随机 jitter 间隔 + 纯正规参数
- 输出：JSONL 格式（含规范化字段名）
"""

import tls_client                # ⚡ tls_client 伪装 Chrome TLS 指纹（比 curl_cffi 更准）
import json
import time
import sys
import random
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

# ── 路径配置 ──────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
CRYPTO_DIR = BASE_DIR / "utils"
sys.path.insert(0, str(BASE_DIR))
from utils.wenshu_crypto import generate_random_salt, encrypt_ciphertext, decrypt_result

# ── 从 session.json 读取登录凭据（由 login_sniffer.py 生成）───────────────
SESSION_FILE = BASE_DIR / "config" / "session.json"
_session_data = {}
if SESSION_FILE.exists():
    with open(SESSION_FILE, "r", encoding="utf-8") as f:
        _session_data = json.load(f)

SESSION_COOKIE   = _session_data.get("session", "")
HOLDONKEY_COOKIE = _session_data.get("holdonkey", "")

if not SESSION_COOKIE:
    print("❌ 未找到 session.json，请先运行 login_auto.py 登录！")
    sys.exit(1)

print(f"📋 已加载: SESSION={SESSION_COOKIE[:16]}... HOLDONKEY={HOLDONKEY_COOKIE[:16] if HOLDONKEY_COOKIE else '无'}...")
CPRQ_START = "2015-06-01"
CPRQ_END   = "2015-06-30"
PAGE_SIZE  = 5  # ⚠️ 不要改！改了日期过滤会失效
LIMIT_MAX  = 600

# ── 输出文件 ──────────────────────────────────────────────────────────────
OUTPUT_FILE     = BASE_DIR / "wenshu_2025july.jsonl"
CHECKPOINT_FILE = BASE_DIR / "crawler_checkpoint.json"

# ── 网络配置 ──────────────────────────────────────────────────────────────
PROXIES = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}
DELAY_MIN = 3.0   # 基础翻页速度（像人一样快速浏览）
DELAY_MAX = 6.0   
MAX_ERRORS = 5    

# ── 字段映射 ──────────────────────────────────────────────────────────────
FIELD_MAP = {
    "1":      "title",       "2":      "court",       "7":      "case_no",
    "9":      "type_code",   "10":     "proc_code",   "26":     "content",
    "31":     "date",        "32":     "extra",       "43":     "source",
    "44":     "flag",        "rowkey": "doc_id",
}


def normalize_doc(raw: dict) -> dict:
    return {FIELD_MAP.get(k, k): v for k, v in raw.items()}


def make_session():
    sess = tls_client.Session(client_identifier="chrome_120", random_tls_extension_order=True)
    sess.proxies = PROXIES

    # 直接设置所有 cookie
    cookie_map = [
        ("SESSION",   SESSION_COOKIE,                     "wenshu.court.gov.cn"),
        ("HOLDONKEY", HOLDONKEY_COOKIE,                   "account.court.gov.cn"),
        ("ncCookie",  _session_data.get("nccookie", ""),  "account.court.gov.cn"),
        ("wzws_reurl",_session_data.get("wzws_reurl", ""),"wenshu.court.gov.cn"),
        ("_bl_uid",   _session_data.get("bl_uid", ""),    "account.court.gov.cn"),
    ]
    for name, value, domain in cookie_map:
        if value:
            sess.cookies.set(name, value, domain=domain)
    return sess


def get_base_headers(target_date: str) -> dict:
    return {
        "accept":           "application/json, text/javascript, */*; q=0.01",
        "accept-language":  "zh-CN,zh;q=0.9,en;q=0.8",
        "content-type":     "application/x-www-form-urlencoded; charset=UTF-8",
        "sec-ch-ua":        '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest":   "empty",
        "sec-fetch-mode":   "cors",
        "sec-fetch-site":   "same-origin",
        "x-requested-with": "XMLHttpRequest",
        "referer": "https://wenshu.court.gov.cn/website/wenshu/181217BMTKHNT2W0/index.html",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    }


def call_q4w(sess, target_date: str, body_str: str, need_cipher: bool = True) -> dict | None:
    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    cipher = encrypt_ciphertext(int(time.time() * 1000), generate_random_salt(24), date_str)
    token = generate_random_salt(24)

    body = body_str + f"&__RequestVerificationToken={token}"
    if need_cipher:
        body += f"&ciphertext={urllib.parse.quote(cipher)}"

    try:
        resp = sess.post(
            "https://wenshu.court.gov.cn/website/parse/rest.q4w",
            headers=get_base_headers(target_date), data=body
        )
        j = resp.json()
        # debug: 打印首次失败的请求
        if j.get("code") != 1 and not hasattr(call_q4w, "_debugged"):
            call_q4w._debugged = True
            print(f"  [DEBUG] body: {body[:300]}")
            cks = {}
            for c in sess.cookies: cks[str(c)] = True
            print(f"  [DEBUG] cookies: SESSION={'SESSION' in cks} wzws={'wzws_reurl' in cks} "
                  f"HOLDONKEY={'HOLDONKEY' in cks} ncCookie={'ncCookie' in cks} _bl_uid={'_bl_uid' in cks}")
            print(f"  [DEBUG] response: {resp.text[:300]}")
        code = j.get("code")
        if code == 1:
            # result 可能是加密字符串，也可能是原生的字典
            if isinstance(j["result"], str):
                dec = decrypt_result(j["result"], j["secretKey"], date_str)
                return json.loads(dec)
            else:
                return j["result"]
        elif code in (9, -9):
            return {"__code9__": True, "desc": j.get("description", "")}
        elif code == -12:
            return {"__code12__": True, "desc": j.get("description", "账号或IP被封禁")}
        else:
            print(f"  ⚠ API code={code}: {j.get('description')}")
            return None
    except Exception as e:
        print(f"  ⚠ 网络异常: {e}")
        return None


# ── 接口A/B：分组统计查询 ──────────────────────────────────────────────────
def api_left_item(sess, date: str, conditions: list, group_fields: str) -> dict | None:
    """获取指定条件下的分组统计"""
    cond_str = urllib.parse.quote(json.dumps(conditions, separators=(',', ':')))
    body = f"queryCondition={cond_str}&groupFields={urllib.parse.quote(group_fields)}&facetLimit=1000&cfg=com.lawyee.judge.dc.parse.dto.SearchDataDsoDTO%40leftDataItem&wh=960&ww=1536&cs=0"
    return call_q4w(sess, date, body, need_cipher=False)


# ── 接口C：子法院字典查询 ──────────────────────────────────────────────────
def api_load_courts(sess, date: str, parent_code: str) -> dict | None:
    """加载子法院列表，返回 {code: name} 映射字典"""
    body = f"parentCode={parent_code}&cfg=com.lawyee.judge.dc.parse.dto.LoadDicDsoDTO%40loadFyByCode&wh=960&ww=1536&cs=0"
    res = call_q4w(sess, date, body, need_cipher=False)
    if isinstance(res, dict) and "__code9__" in res:
        return res
    if isinstance(res, dict) and "fy" in res:
        return {item["code"]: item["name"] for item in res["fy"]}
    return None


# ── 文书查询 ─────────────────────────────────────────────────────────────
def fetch_page(sess, date: str, page_num: int, conditions: list) -> dict | None:
    cond_str = urllib.parse.quote(json.dumps(conditions, separators=(',', ':')))
    body = f"sortFields=s50%3Adesc&pageNum={page_num}&pageSize={PAGE_SIZE}&queryCondition={cond_str}&cfg=com.lawyee.judge.dc.parse.dto.SearchDataDsoDTO%40queryDoc&wh=960&ww=1536&cs=0"
    return call_q4w(sess, date, body, need_cipher=True)


# ── 断点逻辑 ─────────────────────────────────────────────────────────────
def load_checkpoint() -> dict:
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"completed_tasks": [], "current_task_date": None, "current_task_label": None, "last_page": 0, "total_saved": 0}

def save_checkpoint(ckpt: dict):
    ckpt["updated_at"] = datetime.now().isoformat()
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(ckpt, f, ensure_ascii=False, indent=2)

def is_task_completed(ckpt: dict, task_key: str) -> bool:
    return task_key in ckpt["completed_tasks"]

def mark_task_completed(ckpt: dict, task_key: str):
    if task_key not in ckpt["completed_tasks"]:
        ckpt["completed_tasks"].append(task_key)
    ckpt["current_task_date"] = None
    ckpt["current_task_label"] = None
    ckpt["last_page"] = 0
    save_checkpoint(ckpt)

def delay_request(is_page=True):
    if not is_page:
        # 切换省份/法院（模拟退回主页重新点击的过程，耗时稍长）
        delay = random.uniform(5.5, 9.5)
    else:
        # 正常的每页之间点击（相对较快）
        delay = random.uniform(DELAY_MIN, DELAY_MAX)
    time.sleep(delay)


# ── 爬取流程：叶子节点（真正翻页） ───────────────────────────────────────
def crawl_leaf(sess, f, date: str, conditions: list, label: str, total_count: int, ckpt: dict, max_pages: int):
    task_key = f"{date}::{label}"
    if is_task_completed(ckpt, task_key):
        return

    # 限幅 600
    if total_count > LIMIT_MAX:
        print(f"    ⚠️ [警告] {label} 数量超限 ({total_count} > {LIMIT_MAX})，只能截取前 {LIMIT_MAX} 条！")
        total_count = LIMIT_MAX

    total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE
    if max_pages != -1:
        total_pages = min(total_pages, max_pages)

    # 恢复断点
    start_page = 1
    if ckpt["current_task_label"] == label and ckpt["current_task_date"] == date:
        start_page = ckpt["last_page"] + 1

    if start_page > total_pages:
        print(f"    ✅ {label} 已完成（共 {total_count} 条，{total_pages} 页）")
        mark_task_completed(ckpt, task_key)
        return

    print(f"    ▶ 开始抓取 {label} (总条数: {total_count}, 计划页数: {start_page}~{total_pages})")
    
    errors = 0
    for pn in range(start_page, total_pages + 1):
        delay_request(is_page=True)
        
        # 模拟真实人类的“多级疲劳/分心”机制
        if pn > 1:
            # 1. 小分心：每看 6~9 页，低头回个微信（停顿 8~15秒）
            if pn % random.randint(6, 9) == 0:
                short_pause = random.uniform(8.0, 15.0)
                print(f"      📱 模拟分心看手机，暂停 {short_pause:.1f} 秒...")
                time.sleep(short_pause)
            # 2. 大休息：每看 25~35 页，去倒杯水/上个厕所（停顿 30~45秒）
            elif pn % random.randint(25, 35) == 0:
                long_pause = random.uniform(30.0, 45.0)
                print(f"      🚶 模拟人类起立休息，暂停 {long_pause:.1f} 秒...")
                time.sleep(long_pause)

        page_ok = False
        for retry in range(3):
            res = fetch_page(sess, date, pn, conditions)
            if res is None:
                errors += 1
                wait = min(10 * (retry + 1), 60)
                print(f"      [p{pn:03d}] ❌ 网络错误 (retry {retry+1}/3)，等待 {wait}s")
                time.sleep(wait)
                continue
            if res.get("__code9__"):
                wait = 30 * (retry + 1)
                print(f"      [p{pn:03d}] ⚠ code=9 限速/Cookie失效 (retry {retry+1}/3)，等待 {wait}s")
                time.sleep(wait)
                continue
            if res.get("__code12__"):
                print(f"\n      🚨 [致命错误] 触发 code=-12！账号或IP已被裁判文书网风控系统封禁！")
                print(f"      🚨 请立即停止爬取，更换账号或切换IP后再试。")
                sys.exit(1)

            docs = res.get("queryResult", {}).get("resultList", [])
            if not docs:
                # 可能是真没数据了
                pass

            for doc in docs:
                f.write(json.dumps(normalize_doc(doc), ensure_ascii=False) + "\n")
            
            ckpt["total_saved"] += len(docs)
            ckpt["current_task_date"] = date
            ckpt["current_task_label"] = label
            ckpt["last_page"] = pn
            save_checkpoint(ckpt)
            
            print(f"      [p{pn:03d}] 抓取成功 +{len(docs)} 条 | 累计: {ckpt['total_saved']:,}")
            page_ok = True
            errors = 0
            break

        if not page_ok:
            print(f"      🚨 {label} 第 {pn} 页连续失败，当前节点中止！")
            sys.exit(1)

    print(f"    🎉 {label} 节点完成！")
    mark_task_completed(ckpt, task_key)


# ── 爬取流程：具体法院下钻 ───────────────────────────────────────────────
def crawl_court(sess, f, date: str, prov_name: str, court_code: str, court_name: str, count: int, ckpt: dict, max_pages: int):
    label = f"{prov_name}::{court_code}({court_name})"
    task_key = f"{date}::{label}"
    if is_task_completed(ckpt, task_key):
        return

    conditions = [
        {"key": "cprq", "value": f"{date} TO {date}"},
        {"key": "s39", "value": court_code[:3]}, # 省级代码(前三位)
        {"key": "s40", "value": court_code}
    ]

    if count <= LIMIT_MAX:
        # 叶子节点，直接爬
        crawl_leaf(sess, f, date, conditions, label, count, ckpt, max_pages)
    else:
        print(f"    🔍 {label} 数量为 {count} > {LIMIT_MAX}，继续加载下级法院...")
        delay_request(is_page=False)
        sub_courts = api_load_courts(sess, date, court_code)
        
        if sub_courts is None:
            print(f"    🚨 {label} 接口C加载下级法院网络异常，强制转为叶子节点爬取。")
            crawl_leaf(sess, f, date, conditions, label, count, ckpt, max_pages)
            return
        elif isinstance(sub_courts, dict) and sub_courts.get("__code9__"):
            print(f"    🚨 {label} 加载下级法院触发 code=9，退出程序请更新 Cookie。")
            sys.exit(1)
        elif len(sub_courts) == 0:
            print(f"    ⚠️ {label} 无更下级法院可供拆解，只能作为叶子截取前 {LIMIT_MAX} 条。")
            crawl_leaf(sess, f, date, conditions, label, count, ckpt, max_pages)
        else:
            print(f"    ⚠️ 警告: 拆分所有子法庭。")
            for sub_code, sub_name in sub_courts.items():
                sub_label = f"{label}::{sub_code}({sub_name})"
                # 文书网其实不支持单独 s41 下钻如果不带上层，这里简化处理，将 s40 改为 s41
                # 根据分析，Wenshu 的 s41 是基层法庭。如果在 s40 下还要细分，可以直接用 s41.
                sub_conds = [
                    {"key": "cprq", "value": f"{date} TO {date}"},
                    {"key": "s41", "value": sub_code}
                ]
                # 盲爬子法庭（假设最大 600）
                crawl_leaf(sess, f, date, sub_conds, sub_label, LIMIT_MAX, ckpt, max_pages)
            
            mark_task_completed(ckpt, task_key)


# ── 爬取流程：省级下钻 ───────────────────────────────────────────────────
def crawl_province(sess, f, date: str, prov_name: str, count: int, ckpt: dict, max_pages: int):
    task_key = f"{date}::{prov_name}"
    if is_task_completed(ckpt, task_key):
        return

    conditions = [
        {"key": "cprq", "value": f"{date} TO {date}"},
        {"key": "s33", "value": prov_name}
    ]

    if count <= LIMIT_MAX:
        # 省级已经 <= 600，直接作为叶子节点爬取！
        crawl_leaf(sess, f, date, conditions, prov_name, count, ckpt, max_pages)
    else:
        # 省级 > 600，需要调用接口 B 下钻到 s40 (法院)
        print(f"  🔍 {prov_name} 数量为 {count} > {LIMIT_MAX}，正在加载各子法院统计...")
        delay_request(is_page=False)
        group_res = api_left_item(sess, date, conditions, "s39,s40")
        
        if group_res is None or group_res.get("__code9__"):
            print(f"  🚨 获取 {prov_name} 子法院统计失败 (code9={group_res and group_res.get('__code9__')})，请更新 Cookie 或稍后重试。")
            sys.exit(1)
            
        court_counts = {item["value"]: item["count"] for item in group_res.get("s40", [])}
        
        # 还需要调用接口C获取法院名称
        # province 对应的 parentCode 可以从 group_res 里的 s39 拿到！
        s39_list = group_res.get("s39", [])
        if not s39_list:
            print(f"  ⚠️ {prov_name} 无法获取省级代码(s39)，退化为叶子节点。")
            crawl_leaf(sess, f, date, conditions, prov_name, count, ckpt, max_pages)
            return

        prov_code = s39_list[0]["value"] # 例如 北京的 110
        delay_request(is_page=False)
        court_names = api_load_courts(sess, date, prov_code)
        
        if isinstance(court_names, dict) and court_names.get("__code9__"):
            print(f"  🚨 获取 {prov_name} 法院字典触发 code=9。")
            sys.exit(1)
        if not court_names: court_names = {}

        for court_code, c_count in court_counts.items():
            c_name = court_names.get(court_code, "未知法院")
            crawl_court(sess, f, date, prov_name, court_code, c_name, c_count, ckpt, max_pages)
        
        print(f"  🎉 省份 {prov_name} 所有子节点遍历完成！")
        mark_task_completed(ckpt, task_key)


# ── 爬取流程：日期入口 ───────────────────────────────────────────────────
def crawl_date(sess, f, date: str, ckpt: dict, max_pages: int):
    task_key = f"{date}::ALL"
    if is_task_completed(ckpt, task_key):
        return

    print(f"\n========================================================")
    print(f"🚀 正在分析日期: {date}")
    
    # 获取全国各省分布（接口A）
    conditions = [{"key": "cprq", "value": f"{date} TO {date}"}]
    delay_request(is_page=False)
    group_res = api_left_item(sess, date, conditions, "s45;s11;s4;s33;s42;s8;s6;s44")
    
    if group_res is None or group_res.get("__code9__"):
        print(f"🚨 获取 {date} 全国省份分布失败 (code9={group_res and group_res.get('__code9__')})，请更新 Cookie 或稍后重试。")
        sys.exit(1)
        
    provinces = group_res.get("s33", [])
    if not provinces:
        print(f"✅ 日期 {date} 无任何数据返回。")
        mark_task_completed(ckpt, task_key)
        return

    print(f"🗺️  该日涉及 {len(provinces)} 个省份/最高院分支，开始调度...")
    
    # 按照数据量从小到大爬取（可选策略，让小的快速跑完）
    provinces = sorted(provinces, key=lambda x: x["count"])
    
    for prov in provinces:
        p_name = prov["value"]
        p_count = prov["count"]
        crawl_province(sess, f, date, p_name, p_count, ckpt, max_pages)
    
    print(f"🎉 日期 {date} 全部省市抓取完成！")
    mark_task_completed(ckpt, task_key)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="忽略断点，重新开始")
    parser.add_argument("--max-pages", type=int, default=-1, help="叶子节点最大页数")
    args = parser.parse_args()

    start_date = datetime.strptime(CPRQ_START, "%Y-%m-%d")
    end_date   = datetime.strptime(CPRQ_END, "%Y-%m-%d")
    all_dates = [(start_date + timedelta(days=i)).strftime("%Y-%m-%d") 
                 for i in range((end_date - start_date).days + 1)]

    if args.reset:
        if CHECKPOINT_FILE.exists(): CHECKPOINT_FILE.unlink()
        if OUTPUT_FILE.exists(): OUTPUT_FILE.unlink()
        print("🔄 已重置断点和数据文件，从头开始")

    ckpt = load_checkpoint()
    sess = make_session()

    # 启动时先验证 session 有效性
    print("🔍 验证 session...")
    try:
        r = sess.post(
            "https://wenshu.court.gov.cn/website/parse/rest.q4w",
            headers=get_base_headers(""),
            data={"cfg": "com.lawyee.wbsttools.web.parse.dto.AppUserDTO@currentUser"}
        )
        u = r.json().get("result", {})
        nm = u.get("userName") or u.get("realName") or u.get("userId") or ""
        if "anonymous" in str(nm).lower() or not nm:
            print(f"❌ Session 无效 (anonymous)，请重新登录! 响应: {r.text[:200]}")
            sys.exit(1)
        print(f"✅ Session 有效: {nm}")
    except Exception as e:
        print(f"❌ Session 验证请求失败: {e}")
        sys.exit(1)

    if len(ckpt["completed_tasks"]) > 0:
        print(f"♻️  检测到断点：已完成 {len(ckpt['completed_tasks'])} 个节点。当前总计保存 {ckpt['total_saved']:,} 条。")

    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        for target_date in all_dates:
            crawl_date(sess, f, target_date, ckpt, args.max_pages)

    print(f"\n========================================================")
    print(f"🎉 全部任务结束！共写入 {ckpt['total_saved']:,} 条 → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
