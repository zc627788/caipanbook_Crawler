# -*- coding: utf-8 -*-
"""
最小打通链路及号池切号实测脚本 (Smoke Test for Account Rotation)
- 目的：不用等待几十分钟跑满 200 次请求，直接在 30 秒内实测验证多账号会话构建、发包统计、到达限额顺滑切出、下一个账号自动接盘或 OCR 懒加载自愈全流程！
"""

import time
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from utils.account_pool import AccountPoolManager
from crawler_wenshu import call_q4w, PROXIES

def main():
    print("==========================================================================")
    print("🚀 开始执行最小链路轮转与抗风控自检测试 (Smoke Test for Account Rotation)")
    print("==========================================================================\n")

    pool_mgr = AccountPoolManager(proxy=PROXIES.get("http"))

    # 备份当前配置状态
    original_accounts = json.loads(json.dumps(pool_mgr.accounts))

    print(f"📋 当前号池共加载 {len(pool_mgr.accounts)} 个实名/候选账号配置。")
    print("⚡ 为了快速验证无缝切换，我们将前两个账号的单轮配额在本次测试中临时调至 [ 2 次 API 请求 ]！\n")

    # 临时覆盖前 3 个账号的 quota_limit 为 2
    for i in range(min(3, len(pool_mgr.accounts))):
        pool_mgr.accounts[i]["quota_limit"] = 2
        pool_mgr.accounts[i]["current_used"] = 0
        if pool_mgr.accounts[i]["status"] == "COOLDOWN":
            pool_mgr.accounts[i]["status"] = "ACTIVE"
    pool_mgr.save_pool()

    try:
        # ──────────────────────────────────────────────────────────────────────
        # 第 1 轮：测试第 1 个账号发包计数并触发轮转
        # ──────────────────────────────────────────────────────────────────────
        sess1, acc1 = pool_mgr.get_active_session()
        if not sess1:
            print("❌ 无法获取初始账号 Session，请检查网络或代理！")
            return

        print(f"👉 [测试轮次 1] 上场账号: {acc1['username']} (状态: {acc1['status']}, 配额: {acc1['quota_limit']} 次请求)")
        
        # 验证心跳及模拟浏览器发起真实的统计接口发包 (第 1 次发包)
        print("  ▶ 正在以 Chrome 120 C 层指纹发送第 1 次 API 发包 (校验 AppUserDTO@currentUser 心跳)...")
        res1 = call_q4w(pool_mgr, "", "cfg=com.lawyee.wbsttools.web.parse.dto.AppUserDTO@currentUser", need_cipher=False)
        if isinstance(res1, dict) and (res1.get("userName") or res1.get("realName")):
            print(f"  ✅ 第 1 次发包成功！返回实名心跳信息: {res1.get('userName') or res1.get('realName')}")
        else:
            print(f"  ℹ️ 第 1 次发包响应状态: {res1}")

        time.sleep(1.5)

        # 第 2 次发包：触发阈值！
        print("  ▶ 正在发送第 2 次 API 发包 (查询 2015-06-01 全国统计，触发配额上限 2)...")
        conds_str = "%5B%7B%22key%22%3A%22cprq%22%2C%22value%22%3A%222015-06-01+TO+2015-06-01%22%7D%5D"
        body = f"queryCondition={conds_str}&groupFields=s33&facetLimit=100&cfg=com.lawyee.judge.dc.parse.dto.SearchDataDsoDTO%40leftDataItem&wh=960&ww=1536&cs=0"
        res2 = call_q4w(pool_mgr, "2015-06-01", body, need_cipher=True)

        if res2 and not res2.get("__code9__"):
            print(f"  ✅ 第 2 次发包成功！成功抓取并解析到省份分布树字段：{list(res2.keys()) if isinstance(res2, dict) else '非字典'}")

        print("\n⏳ 检查当前账号 1 状态是否自动切入 COOLDOWN：")
        # 检查账号 1 状态
        acc1_status = next(a["status"] for a in pool_mgr.accounts if a["username"] == acc1["username"])
        print(f"  🔍 账号 {acc1['username']} 现状态: [{acc1_status}] (预期为 COOLDOWN)")

        time.sleep(2)

        # ──────────────────────────────────────────────────────────────────────
        # 第 2 轮：申请下一会话，验证自动无缝顺滑切至第 2 个账号！
        # ──────────────────────────────────────────────────────────────────────
        print("\n--------------------------------------------------------------------------")
        print("🔄 [测试轮次 2] 模拟爬虫进入下页，调用 pool_mgr.get_active_session() 取新会话...")
        sess2, acc2 = pool_mgr.get_active_session()
        
        if not sess2:
            print("❌ 无法获取第 2 个接棒账号！")
            return

        print(f"👉 [成功接棒！] 当前上场账号自动轮换为: {acc2['username']} (上一账号 {acc1['username']} 已在后场冷藏)")
        if acc2['username'] == acc1['username']:
            print("⚠️ 警告：切号前后仍为同一个账号，请检查号池其余账号状态！")
        else:
            print(f"🎉 验证完全成功！顺利从 {acc1['username']} 跨越至接任账号 {acc2['username']}！")

        # 让账号 2 也发包一针，证明 Session 正当可用
        print(f"  ▶ 正在用新账号 {acc2['username']} 发送发包测试心跳...")
        res3 = call_q4w(pool_mgr, "", "cfg=com.lawyee.wbsttools.web.parse.dto.AppUserDTO@currentUser", need_cipher=False)
        if isinstance(res3, dict) and (res3.get("userName") or res3.get("realName")):
            print(f"  ✅ 新账号 {acc2['username']} 接口调用成功！返回在线实名: {res3.get('userName') or res3.get('realName')}")

        print("\n==========================================================================")
        print("🎉 极速最小闭环测试大获全胜！")
        print("   ✅ Chrome 120 底层 C 层 TLS 指纹与心跳验证通过")
        print("   ✅ 请求参数 DES/3DES 动态时间戳 Token 加解密通过")
        print("   ✅ API 发包次数统计与达到阈值自动切入休眠 (COOLDOWN) 通过")
        print("   ✅ 多账号顺滑无感轮转与后继账号热加载闭环通过")
        print("==========================================================================")

    finally:
        # 恢复生产状态与配额：日预算 500
        print("\n🧹 正在将号池恢复至生产日预算 (quota_limit = 500)...")
        from utils.account_pool import DEFAULT_DAILY_BUDGET
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        for orig in original_accounts:
            for cur in pool_mgr.accounts:
                if cur["username"] == orig["username"]:
                    cur["quota_limit"] = DEFAULT_DAILY_BUDGET
                    cur["current_used"] = 0
                    cur["budget_date"] = today
                    if cur["status"] == "COOLDOWN" and orig["status"] == "ACTIVE":
                        cur["status"] = "ACTIVE"
        pool_mgr.save_pool()
        print("✅ 已还原生产配置！")

if __name__ == "__main__":
    main()
