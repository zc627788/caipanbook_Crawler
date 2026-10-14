# 裁判文书采集与 CSV 导出

[English](README.md)

这是我做的一个 Python 采集项目，目标是把裁判文书网页里的内容整理成可以筛选、处理的表格。除了请求网页，还做了 Web 请求协议分析、按日期和法院拆分任务、断点记录，以及 JSONL 到 CSV 的导出。

## 实际采集结果

下面是用原项目保存的数据重新运行导出、检查数量后生成的截图。

![原项目数据核验与导出结果](docs/portfolio/project-evidence/audit.png)

2026 年 10 月 14 日检查的这份 JSONL 有 **7,296 条记录，文书 ID 不重复**，数量和断点记录一致。重新导出的 CSV 是 **7,296 行、12 列**；旧 CSV 只有 6,341 行，这次把已经采到、但旧表里还没有的 **955 条**补进了导出文件。

其中 6,854 条有正文，442 条正文为空。这份数据的裁判日期集中在 2015 年 6 月，不能据此说覆盖了全国或全部年份。一部分案件类型仍是源站编码，使用时还需要映射。

这是对已有采集成果的检查，**这次没有重新联网抓取**。完整数据保留在本地；仓库提供了 [20 条脱敏预览](docs/portfolio/project-evidence/redacted-preview.csv) 和 [核验结果](docs/portfolio/project-evidence/verification.json)，可以查看格式、复核数量。公开预览隐藏了姓名、案号、原始标识和正文，列数少于完整导出。

## 我处理的几个问题

- **请求不能直接照搬普通接口。** 参数编码和响应解码单独放在工具模块里，源站变化时方便定位问题。
- **大范围任务中断后不好接着跑。** 按日期、省份和法院拆任务，保存进度，继续运行时有据可查。
- **抓到数据还得整理成能用的文件。** 保留 JSONL，再导出 CSV，检查记录数、重复 ID 和正文缺失情况。

完整 CSV 包含标题、法院、案由、程序、案号、案件类型、发布日期、裁判日期、当事人、正文、源站数量和文书 ID。部分字段在源站缺失时由标题或正文推断，对准确性要求高的用途需要另外抽检。

## 看代码、运行示例

主程序在 `site_wenshu/crawler_wenshu.py`，协议处理在 `site_wenshu/utils/wenshu_crypto.py`，表格导出在 `site_wenshu/tools/export_csv.py`。

不需要网站账号的本地示例：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install pycryptodome
.\.venv\Scripts\python.exe scripts/portfolio_demo.py
```

这个示例用模拟记录验证处理流程，与上面的真实历史采集数据分开。完整配置、数据检查命令和运行说明见 [英文 README](README.md)。

类似需求可以先提供目标网页、要的字段和大概数量。我会先核对一小份样本，再确定完整采集范围、导出格式和更新频率。
