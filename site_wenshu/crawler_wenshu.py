"""
裁判文书网 2025-07 批量爬虫 v2.0 (自适应递归法院树遍历版)
- 断点续爬：支持精确到 [日期::省份::法院]
- 风控：随机 jitter 间隔 + 纯正规参数
- 输出：JSONL 格式（含规范化字段名）
"""

from curl_cffi import requests as cr         # ⚡ curl_cffi 完美伪装 Chrome 120 C 层 TLS 与 HTTP/2 指纹
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
from utils.account_pool import AccountPoolManager
import re

# ── 从 session.json 读取页码标识或默认配置 ─────────────────────────────────────
SESSION_FILE = BASE_DIR / "config" / "session.json"
_session_data = {}
if SESSION_FILE.exists():
    with open(SESSION_FILE, "r", encoding="utf-8") as f:
        _session_data = json.load(f)

PAGE_ID = _session_data.get("page_id") or _session_data.get("pageId") or _session_data.get("PAGE_ID", "")

CPRQ_START = "2015-06-01"
CPRQ_END   = "2015-06-30"
PAGE_SIZE  = 5  # ⚠️ 不要改！改了日期过滤会失效
LIMIT_MAX  = 600

# ── 输出文件 ──────────────────────────────────────────────────────────────
OUTPUT_FILE     = BASE_DIR / "wenshu_2015mon.jsonl"
CHECKPOINT_FILE = BASE_DIR / "crawler_checkpoint.json"

# ── 网络配置 ──────────────────────────────────────────────────────────────
PROXIES = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}
DELAY_MIN = 3.0   # 基础翻页速度（像人一样快速浏览）
DELAY_MAX = 6.0   
MAX_ERRORS = 5    

# ── 分类码与字段映射 ──────────────────────────────────────────────────────
CASE_TYPE_MAP = {
    "1": "刑事案件", "2": "民事案件", "3": "行政案件",
    "4": "赔偿案件", "5": "执行案件", "民事案件": "民事案件",
    "刑事案件": "刑事案件", "行政案件": "行政案件"
}

def normalize_doc(raw: dict, target_count: int = 0) -> dict:
    title = str(raw.get("1", "") or raw.get("title", "") or raw.get("case_name", ""))
    court = str(raw.get("2", "") or raw.get("court", "") or raw.get("court_name", ""))
    case_no = str(raw.get("7", "") or raw.get("case_no", "") or raw.get("case_code_ori", ""))
    
    raw_type = str(raw.get("9", "") or raw.get("type_code", "") or raw.get("case_type", ""))
    case_type = CASE_TYPE_MAP.get(raw_type, raw_type if raw_type else "民事案件")
    
    program = str(raw.get("10", "") or raw.get("proc_code", "") or raw.get("program", "一审"))
    if program == "一审" and case_type == "民事案件":
        program = "民事一审"
    elif program == "一审" and case_type == "刑事案件":
        program = "刑事一审"
        
    judge_date = str(raw.get("31", "") or raw.get("date", "") or raw.get("judge_date", ""))
    content = str(raw.get("26", "") or raw.get("content", ""))
    publish_date = str(raw.get("32", "") or raw.get("publish_date", judge_date))
    
    reason = str(raw.get("reason", ""))
    if not reason:
        m_reason = re.search(r'与[^，。；\n]+?关于?([^，。；\n]{2,20}?)(?:纠纷|一案|一审|二审|民事|刑事|行政|判决书|裁定书)', title)
        if m_reason:
            reason = m_reason.group(1).strip()
        else:
            m_reason2 = re.search(r'([^，。；\n]{2,18}?)(?:纠纷|罪|一案|一审|二审|民事|判决|裁定)', title)
            if m_reason2:
                reason = m_reason2.group(1).strip()
                
    litigant = str(raw.get("litigant", ""))
    if not litigant:
        parties = re.findall(r'((?:原告|被告|上诉人|被上诉人|申请人|被申请人|公诉机关|被告人)[^，。；\n]{2,25})', content)
        if parties:
            litigant = ",".join(parties[:4])
        elif "与" in title:
            litigant = title.split("一审")[0].split("二审")[0].replace("原告", "").replace("被告", "")
            
    return {
        "case_name": title,
        "court_name": court,
        "reason": reason,
        "program": program,
        "case_code_ori": case_no,
        "case_type": case_type,
        "publish_date": publish_date,
        "judge_date": judge_date,
        "litigant": litigant,
        "content": content,
        "doc_id": str(raw.get("rowkey", "") or raw.get("doc_id", "")),
        "target_count": target_count,
        "is_aligned": True
    }


def get_base_headers(target_date: str) -> dict:
    referer = "https://wenshu.court.gov.cn/website/wenshu/181217BMTKHNT2W0/index.html"
    if PAGE_ID:
        referer += f"?pageId={PAGE_ID}"
        if target_date:
            referer += f"&cprqStart={target_date}&cprqEnd={target_date}"

    return {
        "accept":           "application/json, text/javascript, */*; q=0.01",
        "accept-language":  "zh-CN,zh;q=0.9,en;q=0.8",
        "content-type":     "application/x-www-form-urlencoded; charset=UTF-8",
        "sec-ch-ua":        '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest":   "empty",
        "sec-fetch-mode":   "cors",
        "sec-fetch-site":   "same-origin",
        "x-requested-with": "XMLHttpRequest",
        "referer":          referer,
        "user-agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }


def call_q4w(pool_mgr, target_date: str, body_str: str, need_cipher: bool = True) -> dict | None:
    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    cipher = encrypt_ciphertext(int(time.time() * 1000), generate_random_salt(24), date_str)
    token = generate_random_salt(24)

    body = body_str + f"&__RequestVerificationToken={token}"
    if need_cipher:
        body += f"&ciphertext={urllib.parse.quote(cipher)}"

    try:
        if hasattr(pool_mgr, "get_active_session"):
            sess, acc = pool_mgr.get_active_session()
            if not sess:
                print("  🚨 [号池调度] 当前所有账号处于冷却或无有效会话，休眠 30 秒等待解冻...")
                time.sleep(30)
                sess, acc = pool_mgr.get_active_session()
                if not sess:
                    return {"__code9__": True, "desc": "无可用会话"}
            username = acc.get("username", "未知")
        else:
            sess = pool_mgr
            username = "默认单号"

        resp = sess.post(
            "https://wenshu.court.gov.cn/website/parse/rest.q4w",
            headers=get_base_headers(target_date), data=body
        )
        j = resp.json()
        code = j.get("code")
        if code == 1:
            if hasattr(pool_mgr, "report_request"):
                should_switch = pool_mgr.report_request(username, count=1)
                if should_switch:
                    print(f"  ♻️ [限额轮转] 账号 {username} 本轮连续发包已达 200 次安全上限，放回池中休眠 30 分钟。下轮将自动切用新号接棒！")
            if isinstance(j["result"], str):
                dec = decrypt_result(j["result"], j["secretKey"], date_str)
                return json.loads(dec)
            else:
                return j["result"]
        elif code in (9, -9):
            print(f"  ⚠ API返回 code={code} (无权限/Cookie失效): {j.get('description', '')}")
            if hasattr(pool_mgr, "report_error"):
                pool_mgr.report_error(username, code, j.get("description", ""))
            return {"__code9__": True, "desc": j.get("description", ""), "username": username}
        elif code == -12:
            print(f"  🚨 账号 {username} 触发 code=-12！已被风控或单号达限额封锁。")
            if hasattr(pool_mgr, "report_error"):
                pool_mgr.report_error(username, -12, j.get("description", ""))
            return {"__code12__": True, "desc": j.get("description", ""), "username": username}
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
    body = ""
    if PAGE_ID:
        body += f"pageId={PAGE_ID}&"
    if date:
        body += f"cprqStart={date}&cprqEnd={date}&"
    body += f"queryCondition={cond_str}&groupFields={urllib.parse.quote(group_fields)}&facetLimit=1000&cfg=com.lawyee.judge.dc.parse.dto.SearchDataDsoDTO%40leftDataItem&wh=960&ww=1536&cs=0"
    return call_q4w(sess, date, body, need_cipher=True)


# ── 接口C：子法院字典查询 ──────────────────────────────────────────────────
def api_load_courts(sess, date: str, parent_code: str) -> dict | None:
    """加载子法院列表，返回 {code: name} 映射字典"""
    body = ""
    if PAGE_ID:
        body += f"pageId={PAGE_ID}&"
    if date:
        body += f"cprqStart={date}&"
    body += f"parentCode={parent_code}&cfg=com.lawyee.judge.dc.parse.dto.LoadDicDsoDTO%40loadFyByCode&wh=960&ww=1536&cs=0"
    res = call_q4w(sess, date, body, need_cipher=False)
    if isinstance(res, dict) and "__code9__" in res:
        return res
    if isinstance(res, dict) and "fy" in res:
        return {item["code"]: item["name"] for item in res["fy"]}
    return None


# ── 文书查询 ─────────────────────────────────────────────────────────────
def fetch_page(sess, date: str, page_num: int, conditions: list) -> dict | None:
    cond_str = urllib.parse.quote(json.dumps(conditions, separators=(',', ':')))
    body = ""
    if PAGE_ID:
        body += f"pageId={PAGE_ID}&"
    if date:
        body += f"cprqStart={date}&cprqEnd={date}&"
    body += f"sortFields=s50%3Adesc&pageNum={page_num}&pageSize={PAGE_SIZE}&queryCondition={cond_str}&cfg=com.lawyee.judge.dc.parse.dto.SearchDataDsoDTO%40queryDoc&wh=960&ww=1536&cs=0"
    return call_q4w(sess, date, body, need_cipher=True)


# ── 断点逻辑 ─────────────────────────────────────────────────────────────
def load_checkpoint() -> dict:
    default_ckpt = {"completed_tasks": [], "current_task_date": None, "current_task_label": None, "last_page": 0, "total_saved": 0}
    if CHECKPOINT_FILE.exists():
        try:
            with open(CHECKPOINT_FILE, encoding="utf-8") as f:
                data = json.load(f)
                for k, v in default_ckpt.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception:
            pass
    return default_ckpt

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
        for retry in range(6):
            res = fetch_page(sess, date, pn, conditions)
            if res is None:
                errors += 1
                wait = min(10 * (retry + 1), 60)
                print(f"      [p{pn:03d}] ❌ 网络错误 (retry {retry+1}/6)，等待 {wait}s")
                time.sleep(wait)
                continue
            if res.get("__code9__"):
                wait = 10
                print(f"      [p{pn:03d}] ⚠ code=9 触发保护，固定等待 {wait}s 重试或重登录 (retry {retry+1}/6)")
                time.sleep(wait)
                continue
            if res.get("__code12__"):
                print(f"      🚨 账号 {res.get('username')} 遭遇 code=-12！已标记死号 BANNED，立刻切用健康账号...")
                time.sleep(3)
                continue

            docs = res.get("queryResult", {}).get("resultList", [])
            if not docs:
                pass

            for doc in docs:
                f.write(json.dumps(normalize_doc(doc, target_count=total_count), ensure_ascii=False) + "\n")
            
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
            print(f"      🚨 {label} 第 {pn} 页多次异常，暂停 30s 尝试轮转新号继续...")
            time.sleep(30)

    print(f"    🎉 {label} 节点完成！")
    mark_task_completed(ckpt, task_key)


# ── 爬取流程：省级/级联下钻 ───────────────────────────────────────────────────
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
        mark_task_completed(ckpt, task_key)
        return

    # 省级 > 600，使用 s39,s40 获取级联树
    print(f"  🔍 {prov_name} 数量为 {count} > {LIMIT_MAX}，正在获取法院级联树...")
    group_res = None
    for retry in range(6):
        delay_request(is_page=False)
        group_res = api_left_item(sess, date, conditions, "s39,s40")
        if group_res is None or group_res.get("__code9__") or group_res.get("__code12__"):
            wait = 10 if (group_res and group_res.get("__code9__")) else min(20 * (retry + 1), 60)
            print(f"  🚨 获取 {prov_name} 法院树异常 (retry {retry+1}/6)，等待 {wait}s 后由号池自愈或重试...")
            time.sleep(wait)
            continue
        break
        
    if group_res is None or group_res.get("__code9__") or group_res.get("__code12__"):
        print(f"  🚨 连续获取 {prov_name} 法院树失败，退化为叶子节点尝试强制爬取。")
        crawl_leaf(sess, f, date, conditions, prov_name, count, ckpt, max_pages)
        mark_task_completed(ckpt, task_key)
        return

    # 提取 JSON Tree
    tree = group_res.get("s39,s40", [])
    if not tree:
        print(f"  ⚠️ {prov_name} 树结构为空，退化为叶子节点。")
        crawl_leaf(sess, f, date, conditions, prov_name, count, ckpt, max_pages)
        mark_task_completed(ckpt, task_key)
        return

    # 尝试获取本省中级法院字典
    s39_dict = {}
    if tree:
        first_s39 = tree[0].get("value", "")
        if len(first_s39) >= 1:
            prov_code = first_s39[0] + "00"
            delay_request(is_page=False)
            dic_res = api_load_courts(sess, date, prov_code)
            if isinstance(dic_res, dict) and not dic_res.get("__code9__"):
                s39_dict = dic_res

    # 遍历树状结构
    for s39_node in tree:
        s39_code = s39_node.get("value")
        s39_count = s39_node.get("count", 0)
        s39_name = s39_dict.get(s39_code, s39_code)
        s39_label = f"{prov_name}::{s39_name}({s39_code})"
        
        if s39_count <= LIMIT_MAX:
            print(f"    🌟 [中院级下钻] {s39_label} 共 {s39_count} 条 (<= {LIMIT_MAX})，直接捕获！")
            sub_conds = conditions + [{"key": "s39", "value": s39_code}]
            crawl_leaf(sess, f, date, sub_conds, s39_label, s39_count, ckpt, max_pages)
        else:
            print(f"    🔍 [中院级下钻] {s39_label} 数量为 {s39_count} > {LIMIT_MAX}，继续拆分基层法庭...")
            children = s39_node.get("childGroupFieldList")
            if not children:
                print(f"    ⚠️ {s39_label} 共 {s39_count} 条，但无子节点可供下钻，只能退化截断抓取。")
                sub_conds = conditions + [{"key": "s39", "value": s39_code}]
                crawl_leaf(sess, f, date, sub_conds, s39_label, s39_count, ckpt, max_pages)
                continue

            # 尝试获取该中院下的基层法庭字典
            s40_dict = {}
            delay_request(is_page=False)
            dic_res = api_load_courts(sess, date, s39_code)
            if isinstance(dic_res, dict) and not dic_res.get("__code9__"):
                s40_dict = dic_res

            for s40_node in children:
                s40_code = s40_node.get("value")
                s40_count = s40_node.get("count", 0)
                s40_name = s40_dict.get(s40_code, s40_code)
                s40_label = f"{s39_label}::{s40_name}({s40_code})"
                
                print(f"      [基层级下钻] {s40_label} 准备抓取...")
                sub_conds = conditions + [{"key": "s39", "value": s39_code}, {"key": "s40", "value": s40_code}]
                crawl_leaf(sess, f, date, sub_conds, s40_label, s40_count, ckpt, max_pages)

    print(f"  🎉 省份 {prov_name} 完整 JSON Tree 遍历完成！")
    mark_task_completed(ckpt, task_key)



# ── 爬取流程：日期入口 ───────────────────────────────────────────────────
def crawl_date(sess, f, date: str, ckpt: dict, max_pages: int):
    task_key = f"{date}::ALL"
    if is_task_completed(ckpt, task_key):
        return

    print(f"\n========================================================")
    print(f"🚀 正在分析日期: {date}")
    
    # 获取全国各省分布（接口A）带重试自愈
    conditions = [{"key": "cprq", "value": f"{date} TO {date}"}]
    group_res = None
    for retry in range(6):
        delay_request(is_page=False)
        group_res = api_left_item(sess, date, conditions, "s45;s11;s4;s33;s42;s8;s6;s44")
        if group_res is None or group_res.get("__code9__") or group_res.get("__code12__"):
            wait = 10 if (group_res and group_res.get("__code9__")) else min(20 * (retry + 1), 60)
            print(f"🚨 获取 {date} 分布异常 (retry {retry+1}/6)，等待 {wait}s 后由号池自愈或重试...")
            time.sleep(wait)
            continue
        break
        
    if not group_res or group_res.get("__code9__") or group_res.get("__code12__"):
        print(f"❌ 连续 6 次尝试获取 {date} 失败，跳过该日期或需手工干预。")
        return
        
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
    pool_mgr = AccountPoolManager(proxy=PROXIES.get("http"))

    print("🔍 检查号池状态与初始会话...")
    sess, acc = pool_mgr.get_active_session()
    if not sess:
        print("❌ 当前号池中无法找到或自愈出任何有效 Session，退出。")
        sys.exit(1)
    print(f"✅ 号池初次就绪，当前上场账号: {acc['username']}")

    completed = ckpt.get("completed_tasks", [])
    if len(completed) > 0:
        print(f"♻️  检测到断点：已完成 {len(completed)} 个节点。当前总计保存 {ckpt.get('total_saved', 0):,} 条。")

    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        for target_date in all_dates:
            crawl_date(pool_mgr, f, target_date, ckpt, args.max_pages)

    print(f"\n========================================================")
    print(f"🎉 全部任务结束！共写入 {ckpt['total_saved']:,} 条 → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
