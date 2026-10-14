"""Audit an owner-supplied historical JSONL ZIP without publishing raw judgments.

Example: python scripts/audit_local_archive.py INPUT.zip --out LOCAL_OUTPUT
The existing exporter is run on de-identified records. No network requests.
"""
import argparse, collections, contextlib, csv, hashlib, io, json, re, sys, time, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from site_wenshu.tools.export_csv import jsonl_to_csv

def main():
    p=argparse.ArgumentParser();p.add_argument('archive',type=Path);p.add_argument('--out',required=True,type=Path)
    args=p.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True)
    start=time.perf_counter();raw_hash=hashlib.sha256()
    with args.archive.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):raw_hash.update(block)
    parsed=bad=blank=nonempty=total_chars=0
    ids=set();duplicates=missing_id=0;courts={};types=collections.Counter();months=collections.Counter();lengths=[];fields=collections.Counter()
    allowed_types={'刑事案件','民事案件','行政案件','执行案件','赔偿案件','其他案件','非诉保全审查案件','强制清算与破产案件'}
    sanitized=out/'deidentified-input.jsonl'
    with sanitized.open('w',encoding='utf-8') as dest, zipfile.ZipFile(args.archive) as archive:
        members=[i for i in archive.infolist() if not i.is_dir()]
        for info in members:
            with archive.open(info) as stream:
                for line in stream:
                    if not line.strip():blank+=1;continue
                    try:
                        row=json.loads(line.decode('utf-8-sig'))
                        if not isinstance(row,dict):raise ValueError('not object')
                    except (ValueError,UnicodeError):bad+=1;continue
                    parsed+=1;fields.update(row.keys())
                    key=str(row.get('wsKey') or '')
                    if not key:missing_id+=1
                    elif key in ids:duplicates+=1
                    else:ids.add(key)
                    court=str(row.get('s2') or '')
                    if court and court not in courts:courts[court]=f'COURT_{len(courts)+1:04}'
                    text=str(row.get('qwContent') or '');size=len(text);lengths.append(size);total_chars+=size
                    if text.strip():nonempty+=1
                    kind=str(row.get('s8') or '')
                    kind=kind if kind in allowed_types else '其他/未映射'
                    types[kind]+=1
                    # Preserve original field identity rather than guessing date semantics.
                    date=str(row.get('s31') or '')
                    month=date[:7] if re.fullmatch(r'\d{4}-\d{2}-\d{2}',date) else '未解析'
                    months[month]+=1
                    safe={'case_name':f'文书样本 {parsed:06}（标题不公开）','court_name':courts.get(court,'未提供'),'case_code_ori':'[不公开]','case_type':kind,'program':'[不公开]','reason':'[不公开]','publish_date':'[不公开]','judge_date':month,'litigant':'[不公开]','content':f'[原文不公开；原字段长度 {size} 字符]','doc_id':f'SAMPLE_{parsed:06}','target_count':0}
                    dest.write(json.dumps(safe,ensure_ascii=False)+'\n')
    # This log contains court aliases, not names; exporter reconciliation totals are
    # intentionally not treated as official completeness evidence.
    with contextlib.redirect_stdout(io.StringIO()):jsonl_to_csv(str(sanitized),str(out/'deidentified-all.csv'))
    with (out/'deidentified-all.csv').open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f);headers=reader.fieldnames;exported=0;preview=[]
        for row in reader:
            exported+=1
            if len(preview)<20:preview.append(row)
    assert exported==parsed and len(headers)==12
    with (out/'deidentified-preview.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=headers);writer.writeheader();writer.writerows(preview)
    lengths.sort()
    facts={'audit_date':'2026-10-14','provenance':'Historical collection attributed to the owner by owner confirmation; locally audited, not recollected live in this run.','archive_name':args.archive.name,'archive_sha256':raw_hash.hexdigest(),'archive_bytes':args.archive.stat().st_size,'member_declared_bytes':sum(i.file_size for i in members),'zip_members':len(members),'parsed_records':parsed,'invalid_json_lines':bad,'blank_lines':blank,'unique_wsKey':len(ids),'duplicate_wsKey_records':duplicates,'missing_wsKey_records':missing_id,'nonempty_qwContent_records':nonempty,'distinct_nonempty_court_values':len(courts),'content_chars_total':total_chars,'content_chars_median':lengths[len(lengths)//2] if lengths else 0,'case_type_counts':dict(types),'s31_month_counts':dict(sorted(months.items())),'exported_rows':exported,'export_columns':len(headers),'public_preview_rows':len(preview),'elapsed_seconds':round(time.perf_counter()-start,2),'limitations':['One complete archive read and ZIP CRC checked, not all archives.','Content length is the stored qwContent string length; it may include markup.','No claim of official coverage or present-day source access.','Public preview uses aliases and withheld fields; original text, parties, case numbers and document IDs are not shared.']}
    (out/'verification.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(facts,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
