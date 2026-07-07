# 中国裁判文书网 逆向爬虫工程 (caipanbook_Crawler)

本项目是一个针对中国裁判文书网（2025年最新接口）的纯协议级自动化数据爬虫。
项目利用 Python 原生实现了前端加解密算法还原、指纹伪装及高并发/大数据量抓取的重试退避机制。

## ⚠️ 核心使用说明（登录态配置）

由于裁判文书网具有极强的风控体系，且强制使用支付宝实名扫码授权登录。**本仓库内的自动化登录脚本（`login_alipay_qr.py`）受限于高频异地登录极易触发风控熔断，目前可能处于不稳定或不可用状态。**

因此，目前**最稳妥、最有效**的运行方式是**手动从浏览器提取登录态（Cookies）**，硬编码放入爬虫中：

1. 打开浏览器（如 Chrome），手动访问裁判文书网并完成实名登录。
2. 按 `F12` 打开开发者工具，进入 **Network（网络）** 面板。
3. 发起一次任意检索，在抓取到的 `rest.q4w` 请求中，找到 `Cookie` 字段。
4. 将里面的 `SESSION` 和 `HOLDONKEY` 两个核心 Cookie 的值提取出来。
5. 打开 `site_wenshu/crawler_wenshu.py`，将这两个值粘贴替换到如下变量中：
   ```python
   SESSION_COOKIE   = "你的_SESSION_值"
   HOLDONKEY_COOKIE = "你的_HOLDONKEY_值"
   ```
6. **注意：** 同样需要在 `crawler_wenshu.py` 中更新最新的 `PAGE_ID`（该 ID 与检索条件和时效强绑定）。

---

## 🚀 逆向工程思想与架构解析

本项目彻底抛弃了低效且容易被识别的 Selenium/Playwright 等浏览器沙箱自动化工具，直接直捣黄龙，在协议层实现了数据的大规模采集。核心逆向突破点如下：

### 1. 核心加密参数剥离（算法追踪）
文书网的 API（`rest.q4w`）强制要求传入一个基于当时时间生成的 `ciphertext`。
- 我们通过对前端 JS（类似于 JSEncrypt 和 3DES 变种）的调试，剥离出其加密逻辑。
- 逻辑还原为：`时间戳 + 24位随机 Salt + 当前日期` 作为入参进行对称加密混淆。
- **成果：** 在 `utils/wenshu_crypto.py` 中用 Python 完美复现，彻底摆脱了 Node.js / JSDOM 环境。

### 2. 鉴权体系突破（跨域协议分析）
文书网的登录涉及 `wenshu.court.gov.cn` 和 `account.court.gov.cn` 的跨域 Cookie 共享。
- 请求资源需要同时携带 `SESSION`（主站）和 `HOLDONKEY`（用户中心）才能通过网关校验。
- 另外，每次请求需要携带一个通过前端计算或伪造的随机 24 位盐值 `__RequestVerificationToken`。

### 3. 环境伪装与 WAF 对抗
爬取过程中极易触发 `code=9`（服务端限流或设备指纹不匹配）。
- **指纹伪装**：不能使用随机的 `User-Agent` 池，这会立刻被服务端 WAF 拦截！必须将获取 `pageId` 时所用的 UA 提取出来，在爬虫脚本中完全写死保持一致。
- **退避算法（Exponential Backoff）**：遇到 `code=9`，脚本会自动引入 30s -> 60s -> 90s 的休眠等待期，伪装成人类用户的停顿，成功骗过限流器。

### 4. 幽灵级“陷阱”：分页魔咒
- **发现坑点**：如果尝试强行修改请求体中的 `pageSize=15` 来提速，文书网后端不仅不报错，反而会发生“静默风控”，让你的 `cprqStart`（日期过滤条件）直接失效，导致数据返回总量变为 1.6 亿条全库。
- **破解手段**：锁死 `pageSize=5`，通过游标 `pageId` 进行无感深度翻页，并对大时间跨度（按月/按天）进行横向切片。

---

## 🛠️ 项目结构

```text
├── site_wenshu/
│   ├── crawler_wenshu.py       # 核心爬虫主程序（含断点续爬、容错退避逻辑）
│   ├── jsonl_to_csv.py         # 格式转换清洗工具（JSONL 转标准 Excel CSV）
│   ├── login_alipay_qr.py      # 协议级扫码登录尝试脚本（目前建议弃用，改用手工 Cookie）
│   └── utils/
│       └── wenshu_crypto.py    # 核心算法：还原前台的 ciphertext 加密与解密
└── README.md
```

## 👨‍💻 运行方式

1. 安装依赖：`pip install requests pycryptodome`
2. 配置好 `crawler_wenshu.py` 中的 `SESSION`、`HOLDONKEY` 和 `PAGE_ID`。
3. 运行爬虫：
   ```bash
   python site_wenshu/crawler_wenshu.py
   ```
   *如遇中断，再次运行即可自动实现断点续爬。*
