# 🚀 Windows 系统新机器部署与运行完全指南 (Deploy on Windows)

这份文档将手把手带您将整个爬虫工程迁移到另一台 Windows 电脑（如台式机、服务器、笔记本）上并一键跑通！

---

## 第一步：环境准备与源码迁移

1. **迁移项目文件夹**
   把您当前配置好的整个 `site_wenshu` 文件夹（包含 `config/account_pool.json` 里的 6 个实名账号和 `crawler_checkpoint.json` 断点文件）打包通过 U 盘、网盘或直接复制粘贴到新 Windows 电脑的任意英文路径下（例如 `D:\site_wenshu` 或 `C:\site_wenshu`）。

2. **确认 Python 版本**
   新机器上请安装 **Python 3.10 ~ 3.14 (64位)**。安装 Python 时，务必勾选 **`Add Python to PATH` (将 Python 加入系统环境变量)**。
   在终端（CMD 或 PowerShell）中输入以下命令核验：
   ```powershell
   python --version
   ```

---

## 第二步：一键安装所有依赖 (`requirements.txt`)

打开新电脑的 `PowerShell` 或 `CMD` 命令提示符，进入 `site_wenshu` 目录，执行以下安装命令（建议使用清华大学镜像源极速下载）：

```powershell
# 1. 进入项目文件夹 (根据实际存放路径调整)
cd D:\site_wenshu

# 2. 一键安装 Python 依赖库
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/
```

### ⚠️ 关键动作：安装 Playwright 内置 Chromium 浏览器引擎
因为我们的自愈登录引擎底层需要调用 headless Chrome 自动过点选验证码，执行完上面那条 `pip` 后，**务必执行这条命令下载浏览器驱动**：

```powershell
playwright install chromium
```
*(系统会自动从微软官方 CDN 下载约 150MB 的绿色免安装 Chromium 内核，仅需下载一次)*

---

## 第三步：快速自检与一键启动

### 1. 代理或网络检查
打开 `utils/account_pool.py` 第 21 行：
* 如果新电脑**不需要任何本地翻墙代理或校园网直连**，请设置为：
  ```python
  PROXY_SERVER = ""
  ```
* 如果新电脑上也开了本地抓包/转发端口（如 Clash 的 `10808`），请设置为对应的端口：
  ```python
  PROXY_SERVER = "http://127.0.0.1:10808"
  ```

### 2. 跑一轮全息回归测试（推荐测试是否一切就绪）
```powershell
python -u tests/test_smoke_rotation.py
```
*如果输出 `🎉 极速最小闭环测试大获全胜！`，说明底层 TLS C 层伪装、OCR 识别引擎、号池自动切换已 100% 畅通！*

### 3. 正式启动全量爬虫（断点续爬）
随时输入下述一条完整命令即可开始生产级抓取：

```powershell
python -u crawler_wenshu.py
```
*程序会自动读取 `crawler_checkpoint.json` 和已存的 `wenshu_2015mon.jsonl`，接续上一页无缝往后抓取！*

---

## 第四步：随时导出并查看统计表格 (CSV & 对账单)

无论爬虫在后台跑了多久，打开另外一个 PowerShell 窗口，进入目录执行这句话：

```powershell
python -u tools/export_csv.py
```
它会在两秒钟内完成两件事情：
1. 将 `wenshu_2015mon.jsonl` 中几千几万条新数据全部转成 Excel 能够完美阅读的 `wenshu_2015mon.csv`；
2. 在黑框窗口直接打出一张**【各个省份/地方法院：官方报告总数 target_count vs 实际已抓取数量】的审计对账进度的统计报表**！
