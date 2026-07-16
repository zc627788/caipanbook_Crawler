# -*- coding: utf-8 -*-
"""
多账号轮转号池管理器 (AccountPoolManager)

状态：
  ACTIVE   — 当日可用
  EXPIRED  — 会话失效，或当日预算用尽后标记「过期」；次日预算清零后自愈重登再变 ACTIVE
  COOLDOWN — 仅登录自愈连续失败等短冷却（非日预算）
  BANNED   — code=-12 永久隔离

日预算（2026-07 探底结论）：
  单号约 ~850 次 rest.q4w 触发 -12；生产默认每日 500 次安全预算。
  周期按本地自然日：当日跑满 500 → ACTIVE 改为 EXPIRED；跨日 current_used 清零，
  下次任务从 EXPIRED 走登录自愈进入新周期。
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from curl_cffi import requests as cr

BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "config"
POOL_FILE = CONFIG_DIR / "account_pool.json"
SESSION_FILE = CONFIG_DIR / "session.json"
PROXY_SERVER = ""

# 探底后的生产默认：日预算 500（约 0.6 × N_ban≈853）
DEFAULT_DAILY_BUDGET = 500


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _next_midnight_ts() -> int:
    now = datetime.now()
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(nxt.timestamp())


class AccountPoolManager:
    def __init__(self, pool_file=POOL_FILE, proxy=PROXY_SERVER):
        self.pool_file = Path(pool_file)
        self.proxy = proxy or ""
        self.accounts = []
        self._init_pool()

    def _init_pool(self):
        if not self.pool_file.exists():
            init_username = "351-960362863"
            init_session = ""
            init_holdonkey = ""
            if SESSION_FILE.exists():
                try:
                    with open(SESSION_FILE, "r", encoding="utf-8") as f:
                        sdata = json.load(f)
                        init_username = sdata.get("username", init_username)
                        init_session = sdata.get("session", "")
                        init_holdonkey = sdata.get("holdonkey", "")
                except Exception:
                    pass

            self.accounts = [
                {
                    "username": init_username,
                    "password": "",
                    "status": "ACTIVE" if init_session else "EXPIRED",
                    "session": init_session,
                    "holdonkey": init_holdonkey,
                    "quota_limit": DEFAULT_DAILY_BUDGET,
                    "current_used": 0,
                    "total_used": 0,
                    "budget_date": _today_str(),
                    "cooldown_until": 0,
                    "last_heal": int(time.time()) if init_session else 0,
                    "error_count": 0,
                    "current_proxy": self.proxy or "",
                }
            ]
            self.save_pool()
            print(f"📋 已初始化号池: {self.pool_file}")
        else:
            with open(self.pool_file, "r", encoding="utf-8") as f:
                self.accounts = json.load(f)
            changed = False
            for acc in self.accounts:
                # 兼容旧配额：200 / 2000 / 探底 99999 → 日预算 500
                ql = acc.get("quota_limit")
                if ql in (None, 200, 2000, 99999):
                    acc["quota_limit"] = DEFAULT_DAILY_BUDGET
                    changed = True
                if "budget_date" not in acc:
                    acc["budget_date"] = _today_str()
                    changed = True
                if "current_proxy" not in acc:
                    acc["current_proxy"] = ""
                    changed = True
                # 拼写兼容
                if acc.get("status") == "EXPRIED":
                    acc["status"] = "EXPIRED"
                    changed = True
            if changed:
                self.save_pool()

        # 启动时先尝试跨日重置
        self.refresh_daily_budgets()

    def save_pool(self):
        self.pool_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.pool_file, "w", encoding="utf-8") as f:
            json.dump(self.accounts, f, ensure_ascii=False, indent=2)

    def refresh_daily_budgets(self) -> int:
        """
        跨自然日：清零当日计数。
        - 因日预算打成 EXPIRED 的号：保持 EXPIRED，下次 get 时自愈重登 → ACTIVE
        - 登录失败 COOLDOWN 且已到期：解冻为 EXPIRED 以便重登
        返回重置账号数。
        """
        today = _today_str()
        now = int(time.time())
        n = 0
        for acc in self.accounts:
            if acc.get("status") == "BANNED":
                continue
            if acc.get("budget_date") != today:
                old_date = acc.get("budget_date")
                old_used = acc.get("current_used", 0)
                old_status = acc.get("status")
                acc["budget_date"] = today
                acc["current_used"] = 0
                # 日预算打成的 EXPIRED：保持过期，等自愈
                # 短冷却若已过期：改为 EXPIRED 走重登，而不是直接 ACTIVE 复用旧会话
                if acc.get("status") == "COOLDOWN" and now >= int(acc.get("cooldown_until") or 0):
                    acc["status"] = "EXPIRED"
                    acc["cooldown_until"] = 0
                n += 1
                print(
                    f"📅 [日周期重置] {acc['username']}: "
                    f"{old_date or '?'} used={old_used} status={old_status} "
                    f"→ {today} used=0 status={acc.get('status')}"
                )
        if n:
            self.save_pool()
        return n

    def _proxy_for(self, account: dict) -> str:
        return (account.get("current_proxy") or self.proxy or "").strip()

    def _check_and_heal_account(self, account: dict) -> bool:
        print(f"\n⚡ [号池自愈] 账号 {account['username']} Session 缺失/过期，触发登录...")
        try:
            from utils.wenshu_auth import login_account
        except ImportError:
            sys.path.insert(0, str(BASE_DIR))
            from utils.wenshu_auth import login_account

        proxy = self._proxy_for(account)
        res = login_account(account["username"], account["password"], proxy=proxy, max_retries=2)
        if res.get("success"):
            account["session"] = res["session"]
            account["holdonkey"] = res["holdonkey"]
            account["status"] = "ACTIVE"
            account["last_heal"] = int(time.time())
            account["error_count"] = 0
            try:
                with open(SESSION_FILE, "w", encoding="utf-8") as sf:
                    json.dump(
                        {
                            "username": res["username"],
                            "session": res["session"],
                            "holdonkey": res["holdonkey"],
                            "timestamp": int(time.time()),
                            "all_cookies": res["all_cookies"],
                        },
                        sf,
                        ensure_ascii=False,
                        indent=2,
                    )
            except Exception:
                pass
            self.save_pool()
            print(f"✅ 账号 {account['username']} 自愈成功！Session={account['session'][:16]}...")
            return True

        print(f"❌ 账号 {account['username']} 自愈失败: {res.get('error')}")
        account["error_count"] = account.get("error_count", 0) + 1
        if account["error_count"] >= 3:
            # 登录失败短冷却 30 分钟（非日预算）
            account["status"] = "COOLDOWN"
            account["cooldown_until"] = int(time.time()) + 1800
            print(f"⚠️ 账号 {account['username']} 自愈连续失败 3 次，冷却 30 分钟。")
        self.save_pool()
        return False

    def _mark_daily_exhausted(self, acc: dict, reason: str = "日预算"):
        """当日预算用尽：ACTIVE → EXPIRED（过期），次日清零后再自愈。"""
        prev = acc.get("status")
        acc["status"] = "EXPIRED"
        acc["cooldown_until"] = 0
        # 保留 current_used / session 便于审计；跨日 refresh 清零 used，自愈时换新 session
        print(
            f"♻️  [{reason}] 账号 {acc['username']} 今日已用 "
            f"{acc.get('current_used', 0)}/{acc.get('quota_limit', DEFAULT_DAILY_BUDGET)}，"
            f"状态 {prev} → EXPIRED（过期）。次日预算清零后将自动重登再跑。"
        )
        self.save_pool()

    def get_active_session(self) -> tuple:
        """
        选出可用账号并构建 curl_cffi Session。
        返回: (session_instance, account_dict) 或 (None, None)
        """
        self.refresh_daily_budgets()
        now = int(time.time())

        # 1) ACTIVE 且当日预算未满
        for acc in self.accounts:
            if acc.get("status") != "ACTIVE":
                continue
            limit = int(acc.get("quota_limit") or DEFAULT_DAILY_BUDGET)
            used = int(acc.get("current_used") or 0)
            if used >= limit:
                self._mark_daily_exhausted(acc)
                continue
            if not acc.get("session"):
                acc["status"] = "EXPIRED"
                self.save_pool()
                continue
            return self._build_curl_session(acc), acc

        # 2) EXPIRED → 自愈（仍受日预算约束）
        for acc in self.accounts:
            if acc.get("status") != "EXPIRED":
                continue
            limit = int(acc.get("quota_limit") or DEFAULT_DAILY_BUDGET)
            used = int(acc.get("current_used") or 0)
            if used >= limit:
                self._mark_daily_exhausted(acc)
                continue
            if self._check_and_heal_account(acc):
                return self._build_curl_session(acc), acc

        # 3) COOLDOWN 到期解冻（登录失败 30min 或 跨日已在 refresh 处理）
        for acc in self.accounts:
            if acc.get("status") != "COOLDOWN":
                continue
            if now < int(acc.get("cooldown_until") or 0):
                continue
            # 解冻前再看日预算
            limit = int(acc.get("quota_limit") or DEFAULT_DAILY_BUDGET)
            used = int(acc.get("current_used") or 0)
            if used >= limit and acc.get("budget_date") == _today_str():
                # 仍是当日预算满，推到次日
                acc["cooldown_until"] = _next_midnight_ts()
                self.save_pool()
                continue
            print(f"🔓 [号池] 账号 {acc['username']} 冷却结束，恢复 ACTIVE。")
            acc["status"] = "ACTIVE"
            if acc.get("budget_date") != _today_str():
                acc["current_used"] = 0
                acc["budget_date"] = _today_str()
            self.save_pool()
            if not acc.get("session"):
                if self._check_and_heal_account(acc):
                    return self._build_curl_session(acc), acc
                continue
            return self._build_curl_session(acc), acc

        print("🚨 [号池] 无可用账号（均 BANNED / 日预算用尽 / 自愈失败）。")
        return None, None

    def daily_budget_remaining(self) -> int:
        """所有非 BANNED 账号今日剩余预算合计。"""
        self.refresh_daily_budgets()
        total = 0
        for acc in self.accounts:
            if acc.get("status") == "BANNED":
                continue
            limit = int(acc.get("quota_limit") or DEFAULT_DAILY_BUDGET)
            used = int(acc.get("current_used") or 0)
            total += max(0, limit - used)
        return total

    def _build_curl_session(self, account: dict):
        sess = cr.Session(impersonate="chrome120")
        proxy = self._proxy_for(account)
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}

        for name, val, domain in (
            ("SESSION", account.get("session", ""), "wenshu.court.gov.cn"),
            ("HOLDONKEY", account.get("holdonkey", ""), "account.court.gov.cn"),
        ):
            if val:
                sess.cookies.set(name, val, domain=domain)
        return sess

    def report_request(self, account_username: str, count: int = 1) -> bool:
        """
        累加当日发包次数。达日预算返回 True（应停号至次日）。
        """
        self.refresh_daily_budgets()
        for acc in self.accounts:
            if acc["username"] != account_username:
                continue
            acc["current_used"] = int(acc.get("current_used") or 0) + count
            acc["total_used"] = int(acc.get("total_used") or 0) + count
            limit = int(acc.get("quota_limit") or DEFAULT_DAILY_BUDGET)
            if acc["current_used"] >= limit:
                self._mark_daily_exhausted(acc, reason="日预算用尽")
                return True
            self.save_pool()
            return False
        return False

    def report_success(self, account_username: str, count: int = 5) -> bool:
        return self.report_request(account_username, count=1)

    def report_error(self, account_username: str, code: int, desc: str = ""):
        for acc in self.accounts:
            if acc["username"] != account_username:
                continue
            if code in (9, -9):
                acc["error_count"] = int(acc.get("error_count") or 0) + 1
                if acc["error_count"] >= 3:
                    acc["status"] = "EXPIRED"
                    acc["error_count"] = 0
                    print(
                        f"\n⚠️ [号池] 账号 {account_username} 连续 3 次 code={code}，标记 EXPIRED 待重登。"
                    )
                else:
                    print(
                        f"  [号池] 账号 {account_username} code={code} "
                        f"({acc['error_count']}/3)"
                    )
            elif code == -12:
                acc["status"] = "BANNED"
                acc["ban_desc"] = desc or "code=-12"
                acc["banned_at"] = datetime.now().isoformat(timespec="seconds")
                print(
                    f"\n🚨 [号池] 账号 {account_username} code=-12 ({desc})，已 BANNED！"
                )
            elif code == "EXPIRED":
                acc["status"] = "EXPIRED"
                print(f"\n⚠️ [号池] 账号 {account_username} 标记 EXPIRED。")
            self.save_pool()
            break
