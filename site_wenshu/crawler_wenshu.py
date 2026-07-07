"""
裁判文书网 2025-07 批量爬虫 v1.0
- 断点续爬：自动从上次中断位置继续
- 风控：随机 jitter 间隔 + 随机 UA 轮换
- 输出：JSONL 格式（含规范化字段名）
- 字段说明：
    title     = "1"  标题
    court     = "2"  法院
    case_no   = "7"  案号
    content   = "26" 裁判正文（完整全文，无需进详情页）
    date      = "31" 裁判日期
    type_code = "9"  案件类型代码
    proc_code = "10" 审判程序代码
    doc_id    = rowkey 文书唯一ID
"""

import requests
import json
import time
import sys
import os
import random
import urllib.parse
from datetime import datetime
from pathlib import Path

# ── 路径配置 ──────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
CRYPTO_DIR = BASE_DIR / "utils"
sys.path.insert(0, str(BASE_DIR))
from utils.wenshu_crypto import generate_random_salt, encrypt_ciphertext, decrypt_result

# ── Cookie（定期从浏览器刷新）────────────────────────────────────────────
SESSION_COOKIE   = "73cf86ca-a6f7-43f1-b0a6-641c95c71be6"
HOLDONKEY_COOKIE = "YzFhYjcyMjctMTc3Zi00MjEzLThiNTctZDg3MzBhOTM1ODRl"

# ── 查询参数（从浏览器复制，pageSize 必须与 pageId 建立时一致）─────────────
PAGE_ID    = "a9b96816dedd13378a5860906247c7d5"
CPRQ_START = "2025-07-01"
CPRQ_END   = "2025-07-31"
PAGE_SIZE  = 5  # ⚠️ 不要改！改了日期过滤会失效

# ── 输出文件 ──────────────────────────────────────────────────────────────
OUTPUT_FILE     = BASE_DIR / "wenshu_2025july.jsonl"
CHECKPOINT_FILE = BASE_DIR / "crawler_checkpoint.json"

# ── 网络 ──────────────────────────────────────────────────────────────────
PROXIES = {"http": "http://127.0.0.1:10808", "https": "http://127.0.0.1:10808"}

DELAY_MIN = 1.2   # 最小请求间隔（秒）
DELAY_MAX = 2.5   # 最大请求间隔（秒），带随机 jitter
MAX_ERRORS = 8    # 连续错误超过此数停止


QUERY_CONDITION = json.dumps(
    [{"key": "cprq", "value": f"{CPRQ_START} TO {CPRQ_END}"}],
    separators=(',', ':')
)

# ── 字段映射 ──────────────────────────────────────────────────────────────
FIELD_MAP = {
    "1":      "title",       # 标题
    "2":      "court",       # 法院
    "7":      "case_no",     # 案号
    "9":      "type_code",   # 案件类型代码
    "10":     "proc_code",   # 审判程序代码
    "26":     "content",     # 裁判正文（完整全文）
    "31":     "date",        # 裁判日期
    "32":     "extra",       # 备用字段
    "43":     "source",      # 来源标志
    "44":     "flag",        # 标志位
    "rowkey": "doc_id",      # 文书唯一ID
}


def normalize_doc(raw: dict) -> dict:
    """将原始字段 key 转换为可读字段名"""
    doc = {}
    for k, v in raw.items():
        doc[FIELD_MAP.get(k, k)] = v
    return doc


def make_session() -> requests.Session:
    sess = requests.Session()
    sess.cookies.set("SESSION",   SESSION_COOKIE,   domain="wenshu.court.gov.cn")
    sess.cookies.set("HOLDONKEY", HOLDONKEY_COOKIE, domain="account.court.gov.cn")
    return sess


def fetch_page(sess: requests.Session, page_num: int) -> dict | None:
    now      = datetime.now()
    date_str = now.strftime("%Y%m%d")
    cipher   = encrypt_ciphertext(int(time.time() * 1000), generate_random_salt(24), date_str)
    token    = generate_random_salt(24)

    headers = {
        "accept":           "application/json, text/javascript, */*; q=0.01",
        "accept-language":  "zh-CN,zh;q=0.9,en;q=0.8",
        "cache-control":    "no-cache",
        "content-type":     "application/x-www-form-urlencoded; charset=UTF-8",
        "pragma":           "no-cache",
        "sec-ch-ua":        '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest":   "empty",
        "sec-fetch-mode":   "cors",
        "sec-fetch-site":   "same-origin",
        "x-requested-with": "XMLHttpRequest",
        "referer": (
            f"https://wenshu.court.gov.cn/website/wenshu/181217BMTKHNT2W0/index.html"
            f"?pageId={PAGE_ID}&cprqStart={CPRQ_START}&cprqEnd={CPRQ_END}"
        ),
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    }

    body = "&".join([
        f"pageId={PAGE_ID}",
        f"cprqStart={CPRQ_START}",
        f"cprqEnd={CPRQ_END}",
        "sortFields=s50%3Adesc",
        f"ciphertext={urllib.parse.quote(cipher)}",
        f"pageNum={page_num}",
        f"pageSize={PAGE_SIZE}",
        f"queryCondition={urllib.parse.quote(QUERY_CONDITION)}",
        "cfg=com.lawyee.judge.dc.parse.dto.SearchDataDsoDTO%40queryDoc",
        f"__RequestVerificationToken={token}",
        "wh=791", "ww=1536", "cs=0",
    ])

    try:
        resp = sess.post(
            "https://wenshu.court.gov.cn/website/parse/rest.q4w",
            headers=headers, data=body, proxies=PROXIES, timeout=20,
        )
        j = resp.json()
        code = j.get("code")
        if code == 1:
            dec = decrypt_result(j["result"], j["secretKey"], date_str)
            return json.loads(dec)
        elif code == 9:
            # code=9 可能是限速，也可能是 Cookie 失效
            return {"__code9__": True, "desc": j.get("description", "")}
        else:
            print(f"  ⚠ API code={code}: {j.get('description')}")
            return None
    except Exception as e:
        print(f"  ⚠ 网络异常: {e}")
        return None


def load_checkpoint() -> dict:
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"last_page": 0, "total_saved": 0, "total_count": 0}


def save_checkpoint(last_page: int, total_saved: int, total_count: int):
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "last_page":   last_page,
            "total_saved": total_saved,
            "total_count": total_count,
            "updated_at":  datetime.now().isoformat(),
        }, f, ensure_ascii=False, indent=2)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="裁判文书网 2025-07 批量爬虫（断点续爬）")
    parser.add_argument("--reset",     action="store_true", help="忽略断点，从第 1 页重新开始")
    parser.add_argument("--max-pages", type=int, default=-1, help="最多爬取几页（-1=全部）")
    args = parser.parse_args()

    # ── 加载断点 ──────────────────────────────────────────────────────────
    ckpt = load_checkpoint()
    if args.reset:
        ckpt = {"last_page": 0, "total_saved": 0, "total_count": 0}
        print("🔄 已重置断点，从第 1 页开始")
    else:
        if ckpt["last_page"] > 0:
            print(f"♻️  检测到断点：上次完成到第 {ckpt['last_page']} 页，已存 {ckpt['total_saved']} 条，继续...")

    start_page = ckpt["last_page"] + 1
    total_saved = ckpt["total_saved"]
    sess = make_session()

    # ── 第 1 次探测：确认 pageId 有效 + 获取总条数 ─────────────────────────
    for attempt in range(1, 4):  # 最多重试 3 次（处理临时限速）
        print(f"\n[*] 探测第 1 页 (尝试 {attempt}/3)...")
        probe = fetch_page(sess, 1)

        if probe is None:
            print(f"  网络错误，{10}s 后重试...")
            time.sleep(10)
            continue

        if probe.get("__code9__"):
            if attempt < 3:
                wait = 30 * attempt
                print(f"  ⚠ code=9（可能限速），等待 {wait}s 后重试...")
                time.sleep(wait)
                continue
            else:
                print("❌ 连续 code=9，请检查：")
                print("   1. SESSION/HOLDONKEY Cookie 是否最新")
                print("   2. pageId 是否有效（从浏览器 DevTools Network 重新复制）")
                print("   3. 稍等 5 分钟后再试（服务端限速）")
                sys.exit(1)

        # 成功
        break
    else:
        print("❌ 探测失败")
        sys.exit(1)

    qr0         = probe.get("queryResult", {})
    total_count = qr0.get("resultCount", 0)
    total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE

    if total_count == 0 or total_count > 10_000_000:
        print(f"❌ 日期过滤失效（总条数={total_count}），请重新获取 pageId 或刷新 Cookie")
        sys.exit(1)

    if ckpt["total_count"] and ckpt["total_count"] != total_count:
        print(f"⚠️  总条数变化：{ckpt['total_count']} → {total_count}（可能 pageId 已失效，建议 --reset）")

    end_page = total_pages if args.max_pages == -1 else min(start_page + args.max_pages - 1, total_pages)
    eta_sec  = (end_page - start_page + 1) * ((DELAY_MIN + DELAY_MAX) / 2)
    eta_hr   = eta_sec / 3600

    print(f"✅ 总条数: {total_count:,}, 总页数: {total_pages:,}")
    print(f"📋 爬取范围: 第 {start_page} ~ {end_page} 页 (共 {end_page-start_page+1} 页)")
    print(f"⏱  预计耗时: ~{eta_hr:.1f} 小时（间隔 {DELAY_MIN}~{DELAY_MAX}s）")
    print(f"💾 输出文件: {OUTPUT_FILE}")
    print("─" * 64)

    errors       = 0
    file_mode    = "a"  # 追加模式

    with open(OUTPUT_FILE, file_mode, encoding="utf-8") as f:
        # 如果从第 1 页开始，把探测结果也写进去
        if start_page == 1:
            for doc in qr0.get("resultList", []):
                f.write(json.dumps(normalize_doc(doc), ensure_ascii=False) + "\n")
            total_saved += len(qr0.get("resultList", []))
            print(f"[p0001] +{len(qr0.get('resultList',[]))} 条 → 累计 {total_saved:,} / {total_count:,}")
            save_checkpoint(1, total_saved, total_count)
            loop_start = 2
        else:
            loop_start = start_page

        for pn in range(loop_start, end_page + 1):
            delay = random.uniform(DELAY_MIN, DELAY_MAX)
            time.sleep(delay)

            # 每页最多重试 3 次（处理偶发限速）
            page_ok = False
            for retry in range(3):
                result = fetch_page(sess, pn)

                if result is None:
                    # 网络错误
                    errors += 1
                    wait = min(10 * (retry + 1), 60)
                    print(f"[p{pn:05d}] ❌ 网络错误 (retry {retry+1}/3)，等待 {wait}s")
                    time.sleep(wait)
                    continue

                if result.get("__code9__"):
                    # 限速，退避重试
                    wait = 30 * (retry + 1)
                    print(f"[p{pn:05d}] ⚠ code=9 限速 (retry {retry+1}/3)，等待 {wait}s")
                    time.sleep(wait)
                    continue

                # 成功拿到数据
                docs = result.get("queryResult", {}).get("resultList", [])
                cnt  = result.get("queryResult", {}).get("resultCount", 0)

                if cnt > 10_000_000:
                    print(f"\n[p{pn:05d}] ⚠️ 日期过滤失效（cnt={cnt:,}），停止")
                    save_checkpoint(pn - 1, total_saved, total_count)
                    page_ok = False
                    break

                for doc in docs:
                    f.write(json.dumps(normalize_doc(doc), ensure_ascii=False) + "\n")
                total_saved += len(docs)
                errors = 0
                page_ok = True

                pct = total_saved / total_count * 100
                print(f"[第 {pn:05d} 页] 抓取成功 +{len(docs)} 条 | 累计进度: {total_saved:,} / {total_count:,} ({pct:.2f}%) | 准备抓取下一页...")

                f.flush()
                save_checkpoint(pn, total_saved, total_count)
                break  # 成功，跳出 retry 循环

            if not page_ok:
                if result and result.get("__code9__"):
                    print(f"\n连续限速，停止。下次运行从第 {pn} 页继续。")
                    save_checkpoint(pn - 1, total_saved, total_count)
                elif errors >= MAX_ERRORS:
                    print(f"\n连续错误 {MAX_ERRORS} 次，停止。")
                    save_checkpoint(pn - 1, total_saved, total_count)
                break


    print(f"\n{'='*64}")
    pct = total_saved / total_count * 100 if total_count else 0
    print(f"🎉 本次完成！共写入 {total_saved:,} 条 ({pct:.1f}%) → {OUTPUT_FILE}")
    if total_saved < total_count:
        print(f"💡 仍有 {total_count - total_saved:,} 条未完成，直接再次运行脚本即可断点续爬")


if __name__ == "__main__":
    main()
