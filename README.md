# China Judgments Online: collection and CSV export

[中文说明](README.zh-CN.md)

I built this Python project to collect court documents and turn the responses into a usable table. Most of the work sits behind the download: understanding the site's request format, splitting searches into smaller tasks, keeping track of progress, and exporting records consistently.

The repository includes the crawler, protocol helpers, checkpoints and a CSV exporter.

## What the saved data looks like

![Local verification of original crawler output](docs/portfolio/project-evidence/audit.png)

On 14 October 2026, I checked the original `wenshu_2015mon.jsonl` and reran the project's CSV exporter.

| Check | Result |
| --- | --- |
| Saved records / distinct document IDs | 7,296 / 7,296 |
| Records reported by the checkpoint | 7,296 |
| Regenerated CSV | 7,296 rows, 12 columns |
| Previous CSV | 6,341 rows |
| Additional records included in the regenerated CSV | 955 |
| Records with / without body text | 6,854 / 442 |
| Judgment month in this file | June 2015 |

The useful finding was that the JSONL held more records than the older CSV. Re-exporting brought those 955 records into the table, without collecting them again.

The screenshot is a report generated from those saved records. It is **not a new live collection or evidence of complete coverage**. Some source type codes still need mapping, and 442 records have no body text.

See the [verification numbers and input hash](docs/portfolio/project-evidence/verification.json) and [20-row redacted sample](docs/portfolio/project-evidence/redacted-preview.csv). The public sample uses aliases and omits original names, case numbers, IDs and document text, so it has fewer fields than the private export.

## How the collection works

1. Protocol helpers encode request parameters and decode responses.
2. The crawler splits work by date, province and court.
3. Records go into JSONL; checkpoints keep the task progress for later runs.
4. The exporter produces CSV and prints court-level counts for inspection.

The 12 output fields are `case_name`, `court_name`, `reason`, `program`, `case_code_ori`, `case_type`, `publish_date`, `judge_date`, `litigant`, `content`, `target_count` and `doc_id`.

Some missing fields are inferred from titles or text and need checking for uses that depend on exact legal classification. Source-reported counts alone do not establish completeness.

## Try it locally

This example uses **synthetic records** to exercise the crypto helpers and CSV export. It makes no website requests.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install pycryptodome
.\.venv\Scripts\python.exe scripts/portfolio_demo.py
```

Open `docs/portfolio/demo.html` for the result. To export an existing JSONL:

```powershell
python -c "from site_wenshu.tools.export_csv import jsonl_to_csv; jsonl_to_csv('input.jsonl', 'output.csv')"
```

To repeat the data check against a local checkout containing the original data:

```powershell
python scripts/audit_project_output.py "LOCAL_PROJECT" --private-out "LOCAL_PRIVATE_OUTPUT" --public-out "LOCAL_PUBLIC_EVIDENCE"
```

The full export stays in the private output directory. The public output contains aggregate counts and redacted rows.

## Running the crawler

```powershell
python -m pip install -r site_wenshu/requirements.txt
# Only needed for browser-based workflows:
python -m playwright install chromium
```

Before starting `python site_wenshu/crawler_wenshu.py`, review the date range, output paths, proxy, request rates and session configuration. The current crawler uses `curl_cffi`; older `tls_client` notes describe earlier experiments.

Login helpers read `WENSHU_USERNAME`, `WENSHU_PASSWORD`, `WENSHU_PHONE_NUMBER` and, where used, `WENSHU_COUNTRY_CODE`. Keep account values and session files out of Git. These source-specific helpers need review before use; this is not a maintained one-click service. Current live website access was not retested in the data check above.

## Code map

| File | Responsibility |
| --- | --- |
| `site_wenshu/crawler_wenshu.py` | Task traversal, records and checkpoints |
| `site_wenshu/utils/wenshu_crypto.py` | Request encoding and response decoding |
| `site_wenshu/utils/account_pool.py` | Account/session state |
| `site_wenshu/utils/wenshu_auth.py` | Authentication helpers |
| `site_wenshu/tools/export_csv.py` | Field extraction and CSV export |
| `scripts/audit_project_output.py` | Local data checks and redacted evidence |

`site_wenshu/tools/manual_login.py` is a legacy helper with automated handling despite its name. `archive_and_debug/` contains investigation scripts rather than the normal entry point.

For similar work, I would start with the source URL, a field list and a small sample. That gives us something concrete to agree on before estimating a larger run or scheduled updates.

[Original Chinese notes](docs/legacy-readme.zh-CN.md) · [Protocol investigation notes](site_wenshu/doc/wenshu_reverse_and_crawler_guide.md)
