# 中国裁判文书网 逆向爬虫工程 (caipanbook_Crawler)

针对裁判文书网 2025-2026 最新接口的混合协议爬虫。支持**账号密码登录**，自动绕过 WAF 的 TLS 指纹检测。

---

## 快速开始

```bash
# 安装依赖
pip install playwright ddddocr tls_client pycryptodome
playwright install chromium

# 自动登录（Playwright 打开浏览器 + OCR 识别验证码 -> 自动重试 -> 保存 cookie）
python site_wenshu/login_auto.py

# 运行爬虫（自动读取 config/session.json）
python site_wenshu/crawler_wenshu.py
```

---

## 项目结构

```text
site_wenshu/
├── crawler_wenshu.py            # 核心爬虫（tls_client + 断点续爬）
├── login_auto.py                # 全自动账号密码登录（Playwright + OCR）
├── login_sniffer.py             # 手动登录抓包器（提取 cookie + 对比验证）
├── login_account_pwd.py         # 纯协议登录尝试（已弃用）
├── login_alipay_qr.py           # 支付宝扫码登录
├── test_wenshu_api.py           # API 测试脚本
├── jsonl_to_csv.py              # JSONL -> CSV 转换
├── config/
│   └── session.json             # 自动生成的登录凭据
└── utils/
    └── wenshu_crypto.py         # 3DES 加解密 + RSA 密码加密
```

---

## 技术要点

### TLS 指纹绕过（最关键）

服务端 WAF 通过 TLS 握手 JA3 指纹识别客户端：
- `requests` (urllib3) -> `anonymousUser` ❌
- `curl_cffi` (chrome120) -> `anonymousUser` ❌  
- **`tls_client` (chrome_120)** -> 真实用户 ✅

### 账号密码登录流程

`tongyiLogin/authorize` -> `captcha/getBase64` -> RSA 加密密码 -> `/api/login` -> OAuth 回调 -> SESSION 绑定

### API 参数变更（2025 新版）

- 不再需要 `pageId`、`cprqStart`/`cprqEnd` 参数
- 日期条件统一放在 `queryCondition` JSON 中
- 需同时携带 5 个 cookie：`SESSION` + `HOLDONKEY` + `ncCookie` + `wzws_reurl` + `_bl_uid`

### 其他

- `ciphertext`：时间戳 + Salt + 日期的 3DES CBC 加密
- `pageSize=5` 不可改，否则日期过滤静默失效
- 遇到 `code=9/-9` 自动退避重试
