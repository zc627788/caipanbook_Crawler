"""Reconcile a local crawler JSONL with its checkpoint and rerun its exporter.

Raw exports remain in --private-out. Only aggregates/redacted rows go to --public-out.
Usage: python scripts/audit_project_output.py LOCAL_PROJECT --private-out LOCAL_DIR --public-out PUBLIC_DIR
"""
import argparse,collections,contextlib,csv,hashlib,importlib.util,io,json
from pathlib import Path

def read_csv(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('project',type=Path);ap.add_argument('--private-out',type=Path,required=True);ap.add_argument('--public-out',type=Path,required=True);a=ap.parse_args()
    src=a.project/'site_wenshu';a.private_out.mkdir(parents=True,exist_ok=True);a.public_out.mkdir(parents=True,exist_ok=True)
    path=src/'wenshu_2015mon.jsonl';rows=[];bad=0
    for line in path.open(encoding='utf-8-sig'):
        if not line.strip():continue
        try:rows.append(json.loads(line))
        except ValueError:bad+=1
    spec=importlib.util.spec_from_file_location('local_csv_export',src/'tools/export_csv.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    output=a.private_out/'regenerated.csv'
    with contextlib.redirect_stdout(io.StringIO()):module.jsonl_to_csv(str(path),str(output))
    exported=read_csv(output);old=read_csv(src/'wenshu_2015mon.csv');july=read_csv(src/'wenshu_2025july.csv')
    checkpoint=json.loads((src/'crawler_checkpoint.json').read_text(encoding='utf-8-sig'))
    ids=[r.get('doc_id') for r in rows if r.get('doc_id')]
    assert len(exported)==len(rows) and len(exported[0])==12
    assert set(ids)=={r['doc_id'] for r in exported}
    facts={'audit_date':'2026-10-14','source':'Original crawler project output and checkpoint; local verification, not live recollection.','input_file':path.name,'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'input_bytes':path.stat().st_size,'parsed_records':len(rows),'invalid_json_lines':bad,'unique_doc_ids':len(set(ids)),'missing_ids':len(rows)-len(ids),'duplicate_ids':len(ids)-len(set(ids)),'checkpoint_total_saved':checkpoint.get('total_saved'),'checkpoint_completed_tasks':len(checkpoint.get('completed_tasks',[])),'checkpoint_updated_at':checkpoint.get('updated_at'),'export_rows':len(exported),'export_columns':len(exported[0]),'nonempty_content':sum(bool(r['content'].strip()) for r in exported),'empty_content':sum(not r['content'].strip() for r in exported),'distinct_court_values':len({r['court_name'] for r in exported if r['court_name']}),'judge_date_months':dict(collections.Counter(r['judge_date'][:7] for r in exported)),'case_types':dict(collections.Counter(r['case_type'] for r in exported)),'previous_csv_rows':len(old),'rows_added_by_regeneration':len(exported)-len(old),'july_named_csv_rows':len(july),'july_named_csv_actual_months':dict(collections.Counter(r['judge_date'][:7] for r in july)),'exporter_source_matches_repository':(src/'tools/export_csv.py').read_text(encoding='utf-8')==(Path(__file__).resolve().parents[1]/'site_wenshu/tools/export_csv.py').read_text(encoding='utf-8'),'limitations':['This audit validates existing project output, not current live access or official completeness.','The July-named CSV mixes months and is not added to the JSONL total.','Personal fields and original text remain local; public previews use aliases.']}
    aliases={};preview=[]
    for i,r in enumerate(exported[:20],1):
        court=r['court_name'];aliases.setdefault(court,f'COURT_{len(aliases)+1:03}')
        preview.append({'sample_id':f'SAMPLE_{i:03}','court_alias':aliases[court],'case_type':r['case_type'],'judge_month':r['judge_date'][:7],'content_present':bool(r['content'].strip()),'content_chars':len(r['content']),'title':'[不公开]','case_number':'[不公开]','litigants':'[不公开]','source_doc_id':'[不公开]','full_text':'[不公开]'})
    with (a.public_out/'redacted-preview.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(preview[0]));w.writeheader();w.writerows(preview)
    (a.public_out/'verification.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(facts,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
