# -*- coding: utf-8 -*-
"""
裁判文书网 封号阈值探底脚本 (Ban Threshold Probe)

用途：
  - 用 1~2 个专用账号，受控压测 rest.q4w 的「请求间隔」与「日累计次数」
  - 一出现 code=-12 立即停，并把精确 total_used 写入日志

默认双路出口：
  账号 A → http://127.0.0.1:10808 (v2rayN)
  账号 B → 直连 (proxy 为空)

示例：
  # 启动前校验两条出口是否真不同
  python tests/probe_ban_threshold.py --check-egress

  # 账号 A：速率阶梯 (5s → 3s → 1.5s → 0.5s)
  python tests/probe_ban_threshold.py --slot A --mode rate

  # 账号 B：日累计放量，固定 4s 间隔，目标 600
  python tests/probe_ban_threshold.py --slot B --mode volume --interval 4 --target 600

  # 基线：登录后只打 5 次 currentUser，确认实名
  python tests/probe_ban_threshold.py --slot A --mode baseline

  # 强制指定账号/代理
  python tests/probe_ban_threshold.py --username 351-960362863 --proxy http://127.0.0.1:10808 --mode volume --target 100
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

from curl_cffi import requests as cr

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from crawler_wenshu import get_base_headers  # noqa: E402
from utils.account_pool import POOL_FILE  # noqa: E402
from utils.wenshu_auth import login_account  # noqa: E402
from utils.wenshu_crypto import (  # noqa: E402
    decrypt_result,
    encrypt_ciphertext,
    generate_random_salt,
)

# ── 默认 A/B 槽位 ──────────────────────────────────────────────────────────
DEFAULT_SLOTS = {
    "A": {
        "username": "351-960362863",
        "proxy": "http://127.0.0.1:10808",
        "role": "速率探针 (经 v2rayN 10808)",
    },
    "B": {
        "username": "852-52447174",
        "proxy": "",
        "role": "日累计探针 (本机直连)",
    },
}

RATE_LADDER = [
    {"interval": 5.0, "count": 200, "label": "R1-5.0s"},
    {"interval": 3.0, "count": 200, "label": "R2-3.0s"},
    {"interval": 1.5, "count": 200, "label": "R3-1.5s"},
    {"interval": 0.5, "count": 100, "label": "R4-0.5s"},
]
RATE_REST_BETWEEN_STEPS = 15 * 60  # 阶梯间休息 15 分钟

PROBE_LOG_DIR = BASE_DIR / "probe_logs"
PROBE_STATE_DIR = BASE_DIR / "probe_logs" / "state"
RESULTS_MD = BASE_DIR / "doc" / "ban_probe_results.md"

IP_CHECK_URLS = (
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://ipinfo.io/ip",
)


# ── 工具 ──────────────────────────────────────────────────────────────────
def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_dirs():
    PROBE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    PROBE_STATE_DIR.mkdir(parents=True, exist_ok=True)


def proxy_label(proxy: str) -> str:
    return proxy if proxy else "(直连)"


def _clear_process_proxy_env():
    """避免 HTTP_PROXY/ALL_PROXY 把「直连」再次劫持进 10808。"""
    for k in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
        "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    ):
        if k in os.environ:
            del os.environ[k]


def fetch_egress_ip(proxy: str = "", timeout: float = 12.0) -> str:
    """探测出口公网 IP；失败返回空串。"""
    # 直连时强制清空进程内代理环境变量（curl_cffi / 部分库会读它们）
    if not proxy:
        _clear_process_proxy_env()
    sess = cr.Session(impersonate="chrome120")
    if proxy:
        sess.proxies = {"http": proxy, "https": proxy}
    else:
        # 显式禁用代理，防止库回落到环境变量
        sess.proxies = {"http": None, "https": None}
    last_err = None
    for url in IP_CHECK_URLS:
        try:
            r = sess.get(url, timeout=timeout)
            ip = (r.text or "").strip()
            # 粗过滤：必须像 IPv4/IPv6
            if ip and " " not in ip and len(ip) < 64 and ("." in ip or ":" in ip):
                return ip
        except Exception as e:
            last_err = e
            continue
    if last_err:
        print(f"  ⚠ 出口 IP 探测失败: {last_err}")
    return ""


def check_dual_egress(proxy_a: str, proxy_b: str, require_diff: bool = True) -> dict:
    print("═" * 64)
    print("🌐 双路出口 IP 校验")
    print("═" * 64)
    print(f"  路径 A proxy = {proxy_label(proxy_a)}")
    print(f"  路径 B proxy = {proxy_label(proxy_b)}")

    ip_a = fetch_egress_ip(proxy_a)
    ip_b = fetch_egress_ip(proxy_b)
    print(f"  出口 A = {ip_a or '❌ 失败'}")
    print(f"  出口 B = {ip_b or '❌ 失败'}")

    ok = bool(ip_a and ip_b)
    same = ok and (ip_a == ip_b)
    if not ok:
        print("  ❌ 至少一条路径 IP 探测失败。检查 v2rayN / 网络。")
    elif same:
        print("  ❌ 两条路径出口 IP 相同！")
        print("     常见原因：v2rayN 开了系统代理/TUN，直连也被劫持。")
        print("     处理：关闭 TUN/系统代理，仅保留 10808 入站给程序显式使用。")
    else:
        print("  ✅ 两条路径出口不同，可开始 A/B 探底。")

    if require_diff and (not ok or same):
        raise SystemExit(2)

    return {"ip_a": ip_a, "ip_b": ip_b, "same": same, "ok": ok and not same}


# ── 号池读写（只动目标账号，不走 200 轮转） ───────────────────────────────
def load_pool() -> list:
    with open(POOL_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_pool(accounts: list):
    with open(POOL_FILE, "w", encoding="utf-8") as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)


def find_account(accounts: list, username: str) -> dict | None:
    for acc in accounts:
        if acc.get("username") == username:
            return acc
    return None


def prepare_probe_account(username: str, proxy: str) -> dict:
    """
    准备探针账号：
    - 禁止对 BANNED 号开测
    - 抬高 quota_limit，避免生产 COOLDOWN 干扰
    - 写入 current_proxy
    - 若无 session 或 EXPIRED/EXPRIED → 登录自愈
    """
    accounts = load_pool()
    acc = find_account(accounts, username)
    if not acc:
        raise SystemExit(f"❌ 号池中找不到账号 {username}，请先写入 config/account_pool.json")

    status = (acc.get("status") or "").upper()
    if status == "BANNED":
        raise SystemExit(f"❌ 账号 {username} 已是 BANNED，禁止用于探底。换新号。")

    # 兼容拼写 EXPRIED
    if status in ("EXPRIED", "EXPIRED", "COOLDOWN", ""):
        # COOLDOWN 在探底中直接解冻
        acc["status"] = "EXPIRED" if status in ("EXPRIED", "EXPIRED", "") else "ACTIVE"
        if status == "COOLDOWN":
            acc["status"] = "ACTIVE"
            acc["cooldown_until"] = 0
            acc["current_used"] = 0

    acc["quota_limit"] = max(int(acc.get("quota_limit") or 0), 99999)
    acc["current_used"] = int(acc.get("current_used") or 0)
    acc["total_used"] = int(acc.get("total_used") or 0)
    acc["current_proxy"] = proxy or ""
    acc["error_count"] = int(acc.get("error_count") or 0)
    save_pool(accounts)

    need_login = (not acc.get("session")) or (acc.get("status") in ("EXPIRED", "EXPRIED"))
    if need_login:
        print(f"\n⚡ 账号 {username} 需要登录自愈 (proxy={proxy_label(proxy)}) ...")
        res = login_account(username, acc["password"], proxy=proxy or "", max_retries=3)
        if not res.get("success"):
            raise SystemExit(f"❌ 登录失败: {res.get('error')}")
        # 重新加载（login 可能也写了 session.json，但未必写 pool）
        accounts = load_pool()
        acc = find_account(accounts, username)
        acc["session"] = res["session"]
        acc["holdonkey"] = res["holdonkey"]
        acc["status"] = "ACTIVE"
        acc["last_heal"] = int(time.time())
        acc["error_count"] = 0
        acc["current_proxy"] = proxy or ""
        # 登录返回的 username 有时是 realName，保留号池原 username 作为 key
        save_pool(accounts)
        print(f"✅ 登录成功 SESSION={acc['session'][:16]}...")
    else:
        print(f"✅ 复用已有 SESSION={str(acc.get('session', ''))[:16]}... (status={acc.get('status')})")

    return acc


def mark_banned(username: str, desc: str = ""):
    accounts = load_pool()
    acc = find_account(accounts, username)
    if not acc:
        return
    acc["status"] = "BANNED"
    acc["ban_desc"] = desc
    acc["banned_at"] = now_iso()
    save_pool(accounts)
    print(f"🚨 已把 {username} 标记为 BANNED 并写回号池。")


def bump_pool_counters(username: str, ok: bool = True, code=None, desc: str = ""):
    accounts = load_pool()
    acc = find_account(accounts, username)
    if not acc:
        return
    if ok:
        acc["current_used"] = int(acc.get("current_used") or 0) + 1
        acc["total_used"] = int(acc.get("total_used") or 0) + 1
        # 探底期间永不 COOLDOWN
        acc["quota_limit"] = max(int(acc.get("quota_limit") or 0), 99999)
    else:
        if code in (9, -9):
            acc["error_count"] = int(acc.get("error_count") or 0) + 1
            if acc["error_count"] >= 3:
                acc["status"] = "EXPIRED"
                acc["error_count"] = 0
        elif code == -12:
            acc["status"] = "BANNED"
            acc["ban_desc"] = desc
            acc["banned_at"] = now_iso()
    save_pool(accounts)


# ── 会话与发包 ────────────────────────────────────────────────────────────
def build_session(account: dict, proxy: str):
    if not proxy:
        _clear_process_proxy_env()
    sess = cr.Session(impersonate="chrome120")
    if proxy:
        sess.proxies = {"http": proxy, "https": proxy}
    else:
        sess.proxies = {"http": None, "https": None}
    for name, val, domain in (
        ("SESSION", account.get("session", ""), "wenshu.court.gov.cn"),
        ("HOLDONKEY", account.get("holdonkey", ""), "account.court.gov.cn"),
    ):
        if val:
            sess.cookies.set(name, val, domain=domain)
    return sess


def call_api(sess, target_date: str, body_str: str, need_cipher: bool = True) -> dict:
    """
    独立发包（不经 AccountPoolManager），返回结构化结果：
      {ok, code, desc, data, latency_ms, raw}
    """
    date_str = datetime.now().strftime("%Y%m%d")
    token = generate_random_salt(24)
    body = body_str + f"&__RequestVerificationToken={token}"
    if need_cipher:
        cipher = encrypt_ciphertext(int(time.time() * 1000), generate_random_salt(24), date_str)
        body += f"&ciphertext={urllib.parse.quote(cipher)}"

    t0 = time.time()
    try:
        resp = sess.post(
            "https://wenshu.court.gov.cn/website/parse/rest.q4w",
            headers=get_base_headers(target_date),
            data=body,
            timeout=30,
        )
        latency_ms = int((time.time() - t0) * 1000)
        j = resp.json()
        code = j.get("code")
        desc = j.get("description", "") or ""
        if code == 1:
            data = j.get("result")
            if isinstance(data, str) and j.get("secretKey"):
                try:
                    data = json.loads(decrypt_result(data, j["secretKey"], date_str))
                except Exception:
                    pass
            return {"ok": True, "code": 1, "desc": desc, "data": data, "latency_ms": latency_ms}
        return {
            "ok": False,
            "code": code,
            "desc": desc,
            "data": None,
            "latency_ms": latency_ms,
            "code9": code in (9, -9),
            "code12": code == -12,
        }
    except Exception as e:
        return {
            "ok": False,
            "code": "NET",
            "desc": str(e),
            "data": None,
            "latency_ms": int((time.time() - t0) * 1000),
            "code9": False,
            "code12": False,
        }


def body_current_user() -> tuple[str, bool, str]:
    return (
        "cfg=com.lawyee.wbsttools.web.parse.dto.AppUserDTO@currentUser",
        False,
        "currentUser",
    )


def body_query_doc(date: str = "2015-06-01", page_num: int = 1) -> tuple[str, bool, str]:
    conds = urllib.parse.quote(
        json.dumps([{"key": "cprq", "value": f"{date} TO {date}"}], separators=(",", ":"))
    )
    body = (
        f"cprqStart={date}&cprqEnd={date}"
        f"&sortFields=s50%3Adesc&pageNum={page_num}&pageSize=5"
        f"&queryCondition={conds}"
        f"&cfg=com.lawyee.judge.dc.parse.dto.SearchDataDsoDTO%40queryDoc"
        f"&wh=960&ww=1536&cs=0"
    )
    return body, True, "queryDoc"


def body_left_item(date: str = "2015-06-01") -> tuple[str, bool, str]:
    conds = urllib.parse.quote(
        json.dumps([{"key": "cprq", "value": f"{date} TO {date}"}], separators=(",", ":"))
    )
    body = (
        f"cprqStart={date}&cprqEnd={date}"
        f"&queryCondition={conds}&groupFields=s33&facetLimit=100"
        f"&cfg=com.lawyee.judge.dc.parse.dto.SearchDataDsoDTO%40leftDataItem"
        f"&wh=960&ww=1536&cs=0"
    )
    return body, True, "leftDataItem"


def pick_api(api_mode: str, n: int, date: str) -> tuple[str, bool, str, str]:
    """
    返回 (body, need_cipher, api_name, target_date)
    mixed: 每 5 次 1 次 currentUser + 4 次 queryDoc
    """
    if api_mode == "heartbeat":
        b, c, name = body_current_user()
        return b, c, name, ""
    if api_mode == "stats":
        b, c, name = body_left_item(date)
        return b, c, name, date
    if api_mode == "query":
        b, c, name = body_query_doc(date, page_num=((n - 1) % 5) + 1)
        return b, c, name, date
    # mixed
    if n % 5 == 1:
        b, c, name = body_current_user()
        return b, c, name, ""
    b, c, name = body_query_doc(date, page_num=((n - 1) % 5) + 1)
    return b, c, name, date


# ── 日志 / 状态 ───────────────────────────────────────────────────────────
class ProbeLogger:
    def __init__(self, username: str, slot: str, mode: str):
        ensure_dirs()
        day = datetime.now().strftime("%Y%m%d")
        safe_user = username.replace("/", "_")
        self.path = PROBE_LOG_DIR / f"probe_{slot}_{safe_user}_{day}.jsonl"
        self.state_path = PROBE_STATE_DIR / f"state_{slot}_{safe_user}.json"
        self.meta = {
            "username": username,
            "slot": slot,
            "mode": mode,
            "started_at": now_iso(),
        }
        self.success = 0
        self.fail = 0
        self.banned = False
        self.ban_at_n = None
        print(f"📝 日志文件: {self.path}")

    def load_state(self) -> dict:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"total_ok": 0, "total_fail": 0, "history": []}

    def save_state(self, extra: dict | None = None):
        st = self.load_state()
        st["total_ok"] = self.success
        st["total_fail"] = self.fail
        st["banned"] = self.banned
        st["ban_at_n"] = self.ban_at_n
        st["updated_at"] = now_iso()
        if extra:
            st.update(extra)
        self.state_path.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")

    def write(self, row: dict):
        row = {**self.meta, **row, "ts": now_iso()}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        # 实时刷状态
        self.save_state({"last_row": row})


def extract_realname(data) -> str:
    if not isinstance(data, dict):
        return ""
    return str(data.get("userName") or data.get("realName") or data.get("userId") or "")


# ── 运行核心 ──────────────────────────────────────────────────────────────
def run_burst(
    sess,
    account: dict,
    proxy: str,
    logger: ProbeLogger,
    *,
    count: int,
    interval: float,
    api_mode: str,
    date: str,
    step_label: str,
    start_n: int = 1,
    stop_on_ban: bool = True,
    reheal_on_code9: bool = True,
) -> tuple[object, dict, bool]:
    """
    连续发包 count 次。
    返回 (sess, account, banned)
    """
    username = account["username"]
    n = start_n
    end_n = start_n + count - 1
    print(f"\n▶ [{step_label}] 计划请求 #{start_n}~#{end_n} | interval={interval}s | api={api_mode}")

    while n <= end_n:
        body, need_cipher, api_name, target_date = pick_api(api_mode, n, date)
        res = call_api(sess, target_date, body, need_cipher=need_cipher)

        row = {
            "n": n,
            "step": step_label,
            "api": api_name,
            "interval": interval,
            "proxy": proxy or "",
            "egress_note": proxy_label(proxy),
            "ok": res.get("ok"),
            "code": res.get("code"),
            "desc": res.get("desc"),
            "latency_ms": res.get("latency_ms"),
            "total_ok_session": logger.success + (1 if res.get("ok") else 0),
        }

        if res.get("ok"):
            logger.success += 1
            bump_pool_counters(username, ok=True)
            rn = extract_realname(res.get("data"))
            if api_name == "currentUser":
                row["realname"] = rn
                print(f"  [{n:04d}] ✅ {api_name} 实名={rn or '?'}  {res['latency_ms']}ms")
            else:
                # queryDoc 看条数
                docs = 0
                data = res.get("data")
                if isinstance(data, dict):
                    docs = len(data.get("queryResult", {}).get("resultList") or [])
                    if not docs and "s33" in data:
                        docs = len(data.get("s33") or [])
                row["items"] = docs
                print(f"  [{n:04d}] ✅ {api_name} items≈{docs}  {res['latency_ms']}ms  ok累计={logger.success}")
            logger.write(row)
        elif res.get("code12"):
            logger.fail += 1
            logger.banned = True
            logger.ban_at_n = n
            row["banned"] = True
            logger.write(row)
            mark_banned(username, res.get("desc") or "code=-12")
            print(f"  [{n:04d}] 🚨 code=-12 封禁！step={step_label} n={n} ok累计={logger.success} desc={res.get('desc')}")
            logger.save_state({"ban_step": step_label, "ban_interval": interval})
            return sess, account, True
        elif res.get("code9"):
            logger.fail += 1
            bump_pool_counters(username, ok=False, code=9, desc=res.get("desc") or "")
            logger.write(row)
            print(f"  [{n:04d}] ⚠ code=9 会话异常: {res.get('desc')}")
            if reheal_on_code9:
                print("     → 尝试重新登录自愈...")
                acc_fresh = prepare_probe_account(username, proxy)
                sess = build_session(acc_fresh, proxy)
                account = acc_fresh
                # 不增加 n，重试同一序号
                time.sleep(max(interval, 2.0))
                continue
        else:
            logger.fail += 1
            logger.write(row)
            print(f"  [{n:04d}] ❌ code={res.get('code')} {res.get('desc')}")

        n += 1
        if n <= end_n:
            # 轻微 jitter，避免完全等间隔机器人感
            jitter = min(0.15 * interval, 0.4)
            sleep_s = max(0.05, interval + (0 if interval < 0.6 else (time.time() % 1 - 0.5) * jitter * 2))
            time.sleep(sleep_s)

    return sess, account, False


def mode_baseline(sess, account, proxy, logger, args) -> int:
    print("\n══ 模式 baseline：登录态 + 5 次 currentUser ══")
    sess, account, banned = run_burst(
        sess, account, proxy, logger,
        count=5, interval=args.interval, api_mode="heartbeat",
        date=args.date, step_label="baseline",
        stop_on_ban=True,
    )
    if banned:
        return 12
    # 再打 1 次业务
    sess, account, banned = run_burst(
        sess, account, proxy, logger,
        count=1, interval=args.interval, api_mode="query",
        date=args.date, step_label="baseline-query",
        start_n=6,
    )
    print(f"\n✅ baseline 完成 success={logger.success} fail={logger.fail}")
    return 12 if banned else 0


def mode_rate(sess, account, proxy, logger, args) -> int:
    """速率阶梯：严格使用每档自身 interval。"""
    print("\n══ 模式 rate：速率阶梯探底 ══")
    ladder = list(RATE_LADDER)
    if args.rate_start > 0:
        ladder = ladder[args.rate_start - 1 :]
    if args.max_per_step > 0:
        ladder = [{**s, "count": min(s["count"], args.max_per_step)} for s in ladder]

    n_cursor = 1
    for i, step in enumerate(ladder):
        if i > 0 and not args.no_rest:
            rest = args.rest if args.rest > 0 else RATE_REST_BETWEEN_STEPS
            print(f"\n⏸ 阶梯间休息 {rest}s ({rest / 60:.1f} 分钟)...")
            end = time.time() + rest
            while time.time() < end:
                left = int(end - time.time())
                if left % 60 == 0 or left <= 10:
                    print(f"   剩余休息 {left}s ...")
                time.sleep(min(10, max(1, left)))

        interval = step["interval"]
        sess, account, banned = run_burst(
            sess, account, proxy, logger,
            count=step["count"],
            interval=interval,
            api_mode=args.api,
            date=args.date,
            step_label=step["label"],
            start_n=n_cursor,
        )
        if banned:
            print(f"\n🛑 rate 探底在 {step['label']} (interval={interval}s) 触发封禁。n≈{n_cursor}+")
            return 12
        n_cursor += step["count"]
        print(f"✅ 完成 {step['label']} | 本会话 ok={logger.success}")

    print(f"\n🎉 rate 全部阶梯完成，未触发 -12。success={logger.success}")
    return 0


def mode_volume(sess, account, proxy, logger, args) -> int:
    print("\n══ 模式 volume：日累计放量探底 ══")
    interval = args.interval if args.interval > 0 else 4.0
    target = args.target
    checkpoints = sorted({100, 300, 500, 600, 800, 1000, 1200, 1500, 2000, target})
    checkpoints = [c for c in checkpoints if c <= target]
    if target not in checkpoints:
        checkpoints.append(target)
        checkpoints.sort()

    n_cursor = 1
    prev = 0
    for cp in checkpoints:
        batch = cp - prev
        if batch <= 0:
            continue
        print(f"\n—— 目标累计 {cp}（本段 +{batch}）——")
        sess, account, banned = run_burst(
            sess, account, proxy, logger,
            count=batch,
            interval=interval,
            api_mode=args.api,
            date=args.date,
            step_label=f"vol-to-{cp}",
            start_n=n_cursor,
        )
        if banned:
            print(f"\n🛑 volume 探底在累计目标 {cp} 段内触发封禁。成功 ok={logger.success}")
            return 12
        n_cursor += batch
        prev = cp
        print(f"✅ 已达累计 {cp} | ok={logger.success} fail={logger.fail}")
        if args.pause_checkpoint and cp < target:
            print(f"⏸ checkpoint 暂停 {args.pause_checkpoint}s（可 Ctrl+C 人工评估后重跑续传）...")
            time.sleep(args.pause_checkpoint)

    print(f"\n🎉 volume 目标 {target} 完成，未触发 -12。success={logger.success}")
    return 0


# ── CLI ───────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description="文书网封号阈值探底")
    p.add_argument("--check-egress", action="store_true", help="仅校验 A/B 双路出口 IP 后退出")
    p.add_argument("--slot", choices=["A", "B"], help="使用默认槽位 A 或 B")
    p.add_argument("--username", default="", help="覆盖槽位账号")
    p.add_argument("--proxy", default=None, help="覆盖代理，空字符串表示直连。不传则用槽位默认")
    p.add_argument(
        "--mode",
        choices=["baseline", "rate", "volume"],
        default="baseline",
        help="baseline=验活 | rate=速率阶梯 | volume=日累计",
    )
    p.add_argument("--interval", type=float, default=0.0, help="volume/baseline 间隔秒；rate 默认用阶梯")
    p.add_argument("--target", type=int, default=600, help="volume 目标成功请求数")
    p.add_argument(
        "--api",
        choices=["mixed", "query", "heartbeat", "stats"],
        default="mixed",
        help="发包类型，默认 mixed(1 currentUser : 4 queryDoc)",
    )
    p.add_argument("--date", default="2015-06-01", help="业务查询用裁判日期")
    p.add_argument("--rate-start", type=int, default=1, help="rate 从第几阶梯开始(1-based)")
    p.add_argument("--max-per-step", type=int, default=0, help="rate 每阶梯最多请求数(调试用，0=不限)")
    p.add_argument("--no-rest", action="store_true", help="rate 阶梯间不休息")
    p.add_argument("--rest", type=int, default=0, help="rate 阶梯间休息秒数，0=默认 900")
    p.add_argument("--pause-checkpoint", type=int, default=0, help="volume 每个 checkpoint 后暂停秒数")
    p.add_argument("--skip-egress-check", action="store_true", help="跳过启动时的双路出口校验")
    p.add_argument("--skip-login", action="store_true", help="强制不登录，仅用现有 session（危险）")
    p.add_argument(
        "--allow-same-ip",
        action="store_true",
        help="允许 A/B 出口相同仍继续（不推荐）",
    )
    return p.parse_args()


def resolve_slot(args) -> tuple[str, str, str]:
    """返回 username, proxy, slot_name"""
    slot = args.slot or "A"
    conf = DEFAULT_SLOTS[slot]
    username = args.username or conf["username"]
    if args.proxy is None:
        proxy = conf["proxy"]
    else:
        proxy = args.proxy
    return username, proxy, slot


def main():
    args = parse_args()
    ensure_dirs()

    # 仅校验出口
    if args.check_egress:
        check_dual_egress(
            DEFAULT_SLOTS["A"]["proxy"],
            DEFAULT_SLOTS["B"]["proxy"],
            require_diff=not args.allow_same_ip,
        )
        return

    username, proxy, slot = resolve_slot(args)

    print("═" * 64)
    print("🔬 文书网封号阈值探底")
    print("═" * 64)
    print(f"  时间     : {now_iso()}")
    print(f"  槽位     : {slot} ({DEFAULT_SLOTS[slot]['role']})")
    print(f"  账号     : {username}")
    print(f"  代理     : {proxy_label(proxy)}")
    print(f"  模式     : {args.mode}")
    print(f"  API      : {args.api}")
    print(f"  日志目录 : {PROBE_LOG_DIR}")
    print(f"  结果模板 : {RESULTS_MD}")

    # 启动时顺带提示双路差异（不强制，除非未 skip）
    if not args.skip_egress_check:
        try:
            check_dual_egress(
                DEFAULT_SLOTS["A"]["proxy"],
                DEFAULT_SLOTS["B"]["proxy"],
                require_diff=not args.allow_same_ip,
            )
        except SystemExit:
            print("\n如只需单路测试，请加 --skip-egress-check")
            raise

    # 本路出口
    my_ip = fetch_egress_ip(proxy)
    print(f"\n📍 当前槽位实际出口 IP: {my_ip or '探测失败'}")

    if args.skip_login:
        accounts = load_pool()
        acc = find_account(accounts, username)
        if not acc or not acc.get("session"):
            raise SystemExit("skip-login 但无 session")
        account = acc
    else:
        account = prepare_probe_account(username, proxy)

    sess = build_session(account, proxy)
    logger = ProbeLogger(username, slot, args.mode)
    logger.save_state(
        {
            "proxy": proxy,
            "egress_ip": my_ip,
            "mode": args.mode,
            "api": args.api,
        }
    )

    # 首包验活
    print("\n🔎 首包 currentUser 验活...")
    b, c, name = body_current_user()
    res0 = call_api(sess, "", b, need_cipher=c)
    if res0.get("ok"):
        rn = extract_realname(res0.get("data"))
        print(f"  ✅ 实名={rn}  latency={res0['latency_ms']}ms")
        if "匿名" in rn or "anonymous" in rn.lower():
            print("  ⚠ 仍是匿名，尝试强制重登...")
            # 清 session 强制登录
            accounts = load_pool()
            acc = find_account(accounts, username)
            acc["session"] = ""
            acc["status"] = "EXPIRED"
            save_pool(accounts)
            account = prepare_probe_account(username, proxy)
            sess = build_session(account, proxy)
    else:
        print(f"  ⚠ 首包失败 code={res0.get('code')} {res0.get('desc')}，尝试重登...")
        accounts = load_pool()
        acc = find_account(accounts, username)
        if acc:
            acc["session"] = ""
            acc["status"] = "EXPIRED"
            save_pool(accounts)
        account = prepare_probe_account(username, proxy)
        sess = build_session(account, proxy)

    if args.mode == "baseline":
        if args.interval <= 0:
            args.interval = 2.0
        code = mode_baseline(sess, account, proxy, logger, args)
    elif args.mode == "rate":
        code = mode_rate(sess, account, proxy, logger, args)
    else:
        if args.interval <= 0:
            args.interval = 4.0
        code = mode_volume(sess, account, proxy, logger, args)

    print("\n" + "═" * 64)
    print(f"结束 | success={logger.success} fail={logger.fail} banned={logger.banned} ban_at_n={logger.ban_at_n}")
    print(f"请把结论补到: {RESULTS_MD}")
    print("═" * 64)
    sys.exit(code)


if __name__ == "__main__":
    main()
