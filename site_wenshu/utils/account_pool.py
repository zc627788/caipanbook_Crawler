# -*- coding: utf-8 -*-
"""
多账号轮转号池管理器 (AccountPoolManager)
- 自动维护 config/account_pool.json 中 5~6 个账号的生命周期与会话状态
- 支持状态流转：ACTIVE (就绪/作业) <-> COOLDOWN (2000条上限/频率冷却30分) / EXPIRED (需登录) / BANNED (死号封禁)
- 智能自愈：当选中的账号过期或无 Session 时，自动调起 test_wenshu_api.login_account 完成 Chrome 120 原生闭环登录
- 配额控制：单账号单轮连续抓取达到配额 (~2000 条) 时顺滑切出并放回池中休眠
"""

import json
import time
import os
import sys
from pathlib import Path
from curl_cffi import requests as cr

BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "config"
POOL_FILE = CONFIG_DIR / "account_pool.json"
SESSION_FILE = CONFIG_DIR / "session.json"
PROXY_SERVER = ""

class AccountPoolManager:
    def __init__(self, pool_file=POOL_FILE, proxy=PROXY_SERVER):
        self.pool_file = Path(pool_file)
        self.proxy = proxy
        self.accounts = []
        self._init_pool()

    def _init_pool(self):
        """加载或创建初始化号池文件"""
        if not self.pool_file.exists():
            # 尝试从 session.json 读取已有账号做初始化模板
            init_username = "63-9568348610"
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

            default_pool = [
                {
                    "username": init_username,
                    "password": "Zc627788***",
                    "status": "ACTIVE" if init_session else "EXPIRED",
                    "session": init_session,
                    "holdonkey": init_holdonkey,
                    "quota_limit": 200,
                    "current_used": 0,
                    "total_used": 0,
                    "cooldown_until": 0,
                    "last_heal": int(time.time()) if init_session else 0,
                    "error_count": 0
                }
            ]
            # 预留 5 个备用/拓展号池占位（用户可随后修改配置）
            for i in range(1, 6):
                default_pool.append({
                    "username": f"63-956834861{i}",
                    "password": "Zc627788***",
                    "status": "EXPIRED",
                    "session": "",
                    "holdonkey": "",
                    "quota_limit": 200,
                    "current_used": 0,
                    "total_used": 0,
                    "cooldown_until": 0,
                    "last_heal": 0,
                    "error_count": 0
                })
            self.accounts = default_pool
            self.save_pool()
            print(f"📋 已初始化创建多账号号池模板至: {self.pool_file} (含 {len(self.accounts)} 个账号配置)")
        else:
            with open(self.pool_file, "r", encoding="utf-8") as f:
                self.accounts = json.load(f)
            # 兼容并自动把历史的 2000 条限制平滑升级为 200 次请求限制
            for acc in self.accounts:
                if acc.get("quota_limit") == 2000:
                    acc["quota_limit"] = 200
            self.save_pool()

    def save_pool(self):
        """将当前号池状态持久化"""
        self.pool_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.pool_file, "w", encoding="utf-8") as f:
            json.dump(self.accounts, f, ensure_ascii=False, indent=2)

    def _check_and_heal_account(self, account: dict) -> bool:
        """调用 utils.wenshu_auth 执行自愈登录更新会话"""
        print(f"\n⚡ [号池自愈机制] 账号 {account['username']} Session 缺失或过期，自动触发原生协议闭环登录...")
        # 延迟导入以避免循环依赖
        try:
            from utils.wenshu_auth import login_account
        except ImportError:
            sys.path.insert(0, str(BASE_DIR))
            from utils.wenshu_auth import login_account

        res = login_account(account["username"], account["password"], proxy=self.proxy, max_retries=2)
        if res.get("success"):
            account["session"] = res["session"]
            account["holdonkey"] = res["holdonkey"]
            account["status"] = "ACTIVE"
            account["last_heal"] = int(time.time())
            account["error_count"] = 0
            # 同时更新单例 session.json 保持全局兼容
            try:
                with open(SESSION_FILE, "w", encoding="utf-8") as sf:
                    json.dump({
                        "username": res["username"],
                        "session": res["session"],
                        "holdonkey": res["holdonkey"],
                        "timestamp": int(time.time()),
                        "all_cookies": res["all_cookies"]
                    }, sf, ensure_ascii=False, indent=2)
            except Exception:
                pass
            self.save_pool()
            print(f"✅ 账号 {account['username']} 自愈成功！新 Session={account['session'][:16]}...")
            return True
        else:
            print(f"❌ 账号 {account['username']} 自愈失败: {res.get('error')}")
            account["error_count"] = account.get("error_count", 0) + 1
            if account["error_count"] >= 3:
                account["status"] = "COOLDOWN"
                account["cooldown_until"] = int(time.time()) + 1800  # 冷却 30 分钟
                print(f"⚠️ 账号 {account['username']} 自愈连续失败 3 次，转入冷却池 30 分钟。")
            self.save_pool()
            return False

    def get_active_session(self) -> tuple:
        """
        从号池中选出一个有效账号并构建 curl_cffi Session 实例。
        优先级：ACTIVE > EXPIRED (自愈) > COOLDOWN (解冻)
        返回: (session_instance, account_dict)
        """
        now = int(time.time())

        # 第一轮遍历：寻找现成可用的 ACTIVE 账号
        for acc in self.accounts:
            if acc.get("status") == "ACTIVE":
                # 检查配额是否用尽
                if acc.get("current_used", 0) >= acc.get("quota_limit", 200):
                    print(f"♻️  [账号切换] 账号 {acc['username']} 本轮已达发包请求上限 ({acc['current_used']} >= {acc['quota_limit']})，进入冷却休眠(30分钟)。")
                    acc["status"] = "COOLDOWN"
                    acc["cooldown_until"] = now + 1800
                    acc["current_used"] = 0
                    self.save_pool()
                    continue

                # 检查有无实质 session
                if not acc.get("session"):
                    acc["status"] = "EXPIRED"
                else:
                    sess = self._build_curl_session(acc)
                    return sess, acc

        # 第二轮遍历：寻找 EXPIRED 账号发起热自愈
        for acc in self.accounts:
            if acc.get("status") == "EXPIRED" and acc.get("status") != "BANNED":
                if self._check_and_heal_account(acc):
                    sess = self._build_curl_session(acc)
                    return sess, acc

        # 第三轮遍历：若无 ACTIVE 也无能自愈的 EXPIRED，才去检查有没有到期的 COOLDOWN
        for acc in self.accounts:
            if acc.get("status") == "COOLDOWN":
                if now >= acc.get("cooldown_until", 0):
                    print(f"🔓 [号池调度] 账号 {acc['username']} 冷却期已满，解冻恢复为 ACTIVE。")
                    acc["status"] = "ACTIVE"
                    acc["current_used"] = 0
                    self.save_pool()
                    sess = self._build_curl_session(acc)
                    return sess, acc

        print("🚨 [号池告急] 当前号池中所有账号均处于未到期 COOLDOWN 或 BANNED / 自愈失败状态！")
        return None, None

    def _build_curl_session(self, account: dict):
        """构建具体账号对应的 Chrome 120 底层会话"""
        sess = cr.Session(impersonate="chrome120")
        if self.proxy:
            sess.proxies = {"http": self.proxy, "https": self.proxy}

        cookie_map = [
            ("SESSION", account.get("session", ""), "wenshu.court.gov.cn"),
            ("HOLDONKEY", account.get("holdonkey", ""), "account.court.gov.cn")
        ]
        for name, val, domain in cookie_map:
            if val:
                sess.cookies.set(name, val, domain=domain)
        return sess

    def report_request(self, account_username: str, count: int = 1) -> bool:
        """
        报告发包请求次数累加（任何调往 rest.q4w 的请求都会被统计）。
        若到达配额阈值 (200次发包)，把账号切入休眠并返回 True 提示即时交棒。
        """
        for acc in self.accounts:
            if acc["username"] == account_username:
                acc["current_used"] = acc.get("current_used", 0) + count
                acc["total_used"] = acc.get("total_used", 0) + count
                if acc["current_used"] >= acc.get("quota_limit", 200):
                    acc["status"] = "COOLDOWN"
                    acc["cooldown_until"] = int(time.time()) + 1800
                    acc["current_used"] = 0
                    self.save_pool()
                    return True
                self.save_pool()
                return False
        return False

    def report_success(self, account_username: str, count: int = 5) -> bool:
        """报告成功数据条目（保留兼容）"""
        return self.report_request(account_username, count=1)

    def report_error(self, account_username: str, code: int, desc: str = ""):
        """报告异常状态：处理 code=9 短时冷却/过期与 code=-12 永久死号标记"""
        now = int(time.time())
        for acc in self.accounts:
            if acc["username"] == account_username:
                if code in (9, -9):
                    acc["error_count"] = acc.get("error_count", 0) + 1
                    if acc["error_count"] >= 3:
                        acc["status"] = "EXPIRED"
                        acc["error_count"] = 0
                        print(f"\n⚠️ [号池管控] 账号 {account_username} 连续 3 次触发 code={code}，正式标记 EXPIRED 准备重登录！")
                    else:
                        print(f"  [号池管控] 账号 {account_username} 触发 code={code} (错误计数: {acc['error_count']}/3)")
                elif code == -12:
                    acc["status"] = "BANNED"
                    print(f"\n🚨 [号池管控] 严重警告！账号 {account_username} 触发 code=-12 ({desc})，已放入死号池标记 BANNED 永久隔离！")
                elif code == "EXPIRED":
                    acc["status"] = "EXPIRED"
                    print(f"\n⚠️ [号池管控] 账号 {account_username} 会话核验匿名/过期，标记 EXPIRED 待下一轮自动登录热自愈。")
                self.save_pool()
                break
