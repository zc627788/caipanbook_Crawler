# Complex Website Data Extraction & Protocol Analysis

**A Python case study in converting a complex, session-based document website into structured, resumable data collection.**

The project targets China Judgments Online. Its engineering focus is request/response protocol analysis, session handling, hierarchical task partitioning, checkpoint recovery and consistent JSONL/CSV output.

## Client problem and delivery

| Challenge | Implementation in this repository |
| --- | --- |
| Browser requests contain encoded/encrypted parameters | Dedicated request encoding and response decoding functions |
| Data is partitioned by date, province and court | Hierarchical traversal and task-level progress tracking |
| Long tasks may stop or encounter response errors | Checkpoints, bounded retries and error-state handling |
| Raw records use inconsistent field names | A normalized schema and CSV export utility |
| Handover must be inspectable | Source code, operating notes and an offline demonstration |

## Verified original project output — 14 October 2026

![Original project output audit](docs/portfolio/project-evidence/audit.png)

The local crawler project's `wenshu_2015mon.jsonl` contains **7,296 records with 7,296 distinct document IDs**, matching the checkpoint's `total_saved=7296`. Running the project's existing CSV exporter again produced **7,296 rows × 12 columns**, compared with 6,341 rows in the older CSV: **955 additional rows were recovered from the existing JSONL**. The local and repository exporters are identical after line-ending normalization.

The regenerated export contains **1,040 distinct nonempty court-field values**, **6,854 records with body text**, and **442 without body text**. All normalized judgment dates fall in June 2015. No JSON parse failures, missing document IDs or duplicate IDs were found in this input. Type fields include unmapped source codes; they are not represented as fully normalized categories.

This is a local verification of **existing crawler output**, not a claim of current live website access or official completeness. A separate file named `wenshu_2025july.csv` mixes 425 July-2025 records with 5,443 June-2015 records and is not added to the total above. The previously referenced download-folder archive is excluded from this project's evidence.

Inspect the [audit facts and input hash](docs/portfolio/project-evidence/verification.json) and [20-row redacted preview](docs/portfolio/project-evidence/redacted-preview.csv). Original titles, parties, case numbers, document IDs and body text remain local. The preview is a reduced public schema, while the verified private export uses the original 12 columns.

Reproduce against an authorized local checkout containing the original data:

```powershell
python scripts/audit_project_output.py "LOCAL_PROJECT" --private-out "LOCAL_PRIVATE_OUTPUT" --public-out "LOCAL_PUBLIC_EVIDENCE"
```

The script reads the checkpoint and original JSONL, runs the reviewed local exporter, reconciles IDs and counts, and emits only aggregate metrics and a redacted preview into the public output directory. Raw exports must remain private.

## Reproducible offline demonstration

![Offline protocol and export demonstration](docs/portfolio/demo.png)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install pycryptodome
.\.venv\Scripts\python.exe scripts/portfolio_demo.py
```

This runs the repository's crypto helpers and CSV exporter against **synthetic fixtures**. It checks request encoding, encrypted-response decoding, and tabular export without logging in or contacting the source site. Open `docs/portfolio/demo.html` for the report. These local checks do not demonstrate current website access, collection speed or production coverage.

## Current implementation map

| Path | Purpose |
| --- | --- |
| `site_wenshu/crawler_wenshu.py` | Main crawler, field normalization, date/province/court traversal and checkpoints |
| `site_wenshu/utils/wenshu_crypto.py` | Request encoding and response decryption |
| `site_wenshu/utils/account_pool.py` | Session/account state management |
| `site_wenshu/utils/wenshu_auth.py` | Authentication helper implementation |
| `site_wenshu/tools/manual_login.py` | Legacy browser login helper; despite its filename, it contains automated login/CAPTCHA handling |
| `site_wenshu/tools/export_csv.py` | JSONL-to-CSV conversion and reconciliation output |
| `site_wenshu/archive_and_debug/` | Historical diagnostic scripts, not the supported entry point |

The current crawler imports **curl_cffi**. Older notes discussing `tls_client` describe previous experiments and should not be treated as the current dependency or startup guide.

## Preparing a live deployment

Install dependencies from `site_wenshu/requirements.txt` in an isolated environment, and install the Playwright browser only if the selected workflow needs it:

```powershell
python -m pip install -r site_wenshu/requirements.txt
python -m playwright install chromium
```

Before running `python site_wenshu/crawler_wenshu.py`, review the source-specific configuration and constants: date range, output filenames, local proxy, request rates, session inputs and access requirements. This is a developer-oriented project, not a one-command hosted service. Legacy diagnostic scripts should not be run blindly.

Login helpers now read local account values from `WENSHU_USERNAME`, `WENSHU_PASSWORD`, `WENSHU_PHONE_NUMBER` and, where used, `WENSHU_COUNTRY_CODE`. Do not commit real account values, cookies or session files. Some helpers require additional review before use. A client engagement must define the permitted sources, authorized account access and applicable access limits; this portfolio does not promise unrestricted access or universal CAPTCHA/WAF bypass.

For an existing JSONL export:

```powershell
python -c "from site_wenshu.tools.export_csv import jsonl_to_csv; jsonl_to_csv('input.jsonl', 'output.csv')"
```

## Deliverable schema

The exporter produces columns such as `case_name`, `court_name`, `case_code_ori`, `case_type`, `publish_date`, `judge_date`, `content`, `target_count` and `doc_id`. Dataset contents and permitted fields should be agreed before collection; example portfolio data is fictional.

## What this case study demonstrates

Protocol debugging, source-specific Python automation, task partitioning, failure recovery and structured data delivery. Current live availability and a client's exact scope require a separate feasibility check. No client identity, collection volume, uptime or success-rate claim is inferred from the presence of code.

[Historical Chinese notes](docs/legacy-readme.zh-CN.md) · [Technical investigation notes](site_wenshu/doc/wenshu_reverse_and_crawler_guide.md)
