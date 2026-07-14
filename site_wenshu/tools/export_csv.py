import json
import csv
import sys
import os
import re

# 分类码映射字典
CASE_TYPE_MAP = {
    "1": "刑事案件", "2": "民事案件", "3": "行政案件",
    "4": "赔偿案件", "5": "执行案件", "民事案件": "民事案件",
    "刑事案件": "刑事案件", "行政案件": "行政案件"
}

def jsonl_to_csv(jsonl_path, csv_path):
    if not os.path.exists(jsonl_path):
        print(f"Error: {jsonl_path} does not exist.")
        return

    # 对齐 cpws_2015_judge_date_2015_06_sample_100.csv 的 10 个标准列 + 审计列
    headers = [
        "case_name", "court_name", "reason", "program", "case_code_ori",
        "case_type", "publish_date", "judge_date", "litigant", "content",
        "target_count", "doc_id"
    ]
    
    court_stats = {}
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f_in, \
             open(csv_path, "w", encoding="utf-8-sig", newline="") as f_out:
            
            writer = csv.DictWriter(f_out, fieldnames=headers, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            
            count = 0
            for line in f_in:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    
                    # 支持直接读取已对齐的数据或从旧版格式兼容提取
                    title = str(data.get("case_name", "") or data.get("title", "") or data.get("1", ""))
                    court = str(data.get("court_name", "") or data.get("court", "") or data.get("2", ""))
                    case_no = str(data.get("case_code_ori", "") or data.get("case_no", "") or data.get("7", ""))
                    
                    raw_type = str(data.get("case_type", "") or data.get("type_code", "") or data.get("9", ""))
                    case_type = CASE_TYPE_MAP.get(raw_type, raw_type if raw_type else "民事案件")
                    
                    program = str(data.get("program", "") or data.get("proc_code", "") or data.get("10", "一审"))
                    if program == "一审" and case_type == "民事案件":
                        program = "民事一审"
                    elif program == "一审" and case_type == "刑事案件":
                        program = "刑事一审"
                        
                    judge_date = str(data.get("judge_date", "") or data.get("date", "") or data.get("31", ""))
                    content = str(data.get("content", "") or data.get("26", ""))
                    publish_date = str(data.get("publish_date", "") or data.get("32", "") or judge_date)
                    
                    reason = str(data.get("reason", ""))
                    if not reason:
                        m_reason = re.search(r'与[^，。；\n]+?关于?([^，。；\n]{2,20}?)(?:纠纷|一案|一审|二审|民事|刑事|行政|判决书|裁定书)', title)
                        if m_reason:
                            reason = m_reason.group(1).strip()
                        else:
                            m_reason2 = re.search(r'([^，。；\n]{2,18}?)(?:纠纷|罪|一案|一审|二审|民事|判决|裁定)', title)
                            if m_reason2:
                                reason = m_reason2.group(1).strip()
                                
                    litigant = str(data.get("litigant", ""))
                    if not litigant:
                        parties = re.findall(r'((?:原告|被告|上诉人|被上诉人|申请人|被申请人|公诉机关|被告人)[^，。；\n]{2,25})', content)
                        if parties:
                            litigant = ",".join(parties[:4])
                        elif "与" in title:
                            litigant = title.split("一审")[0].split("二审")[0].replace("原告", "").replace("被告", "")
                            
                    target_count_raw = data.get("target_count", 0)
                    try:
                        target_count = int(target_count_raw) if target_count_raw else 0
                    except (ValueError, TypeError):
                        target_count = 0
                    
                    doc_id = str(data.get("doc_id", "") or data.get("rowkey", ""))
                    
                    row = {
                        "case_name": title.replace("\r", "").replace("\n", " "),
                        "court_name": court.replace("\r", "").replace("\n", " "),
                        "reason": reason.replace("\r", "").replace("\n", " "),
                        "program": program.replace("\r", "").replace("\n", " "),
                        "case_code_ori": case_no.replace("\r", "").replace("\n", " "),
                        "case_type": case_type.replace("\r", "").replace("\n", " "),
                        "publish_date": publish_date.replace("\r", "").replace("\n", " "),
                        "judge_date": judge_date.replace("\r", "").replace("\n", " "),
                        "litigant": litigant.replace("\r", "").replace("\n", " "),
                        "content": content.replace("\r", "").replace("\n", " "),
                        "target_count": target_count,
                        "doc_id": doc_id
                    }
                    writer.writerow(row)
                    count += 1

                    # 审计统计追踪
                    if court not in court_stats:
                        court_stats[court] = {"actual": 0, "target": 0}
                    court_stats[court]["actual"] += 1
                    if target_count > court_stats[court]["target"]:
                        court_stats[court]["target"] = target_count

                except Exception as e:
                    print(f"Skipping bad line: {e}")
            
            print(f"\n🎉 成功将 {count:,} 条文书记录导出至: {csv_path}\n")
            print("==========================================================================")
            print("📊 [对账审计报告] 各地方法院：官方报告应有总量 (target_count) vs 实际抓取数")
            print("==========================================================================")
            print(f"{'审判地方法院':<25} | {'官方报告总量':<12} | {'实际已抓取':<10} | {'对账进度':<10}")
            print("-" * 65)
            # 排序打印前 15 个及概括
            sorted_stats = sorted(court_stats.items(), key=lambda x: x[1]["actual"], reverse=True)
            for c_name, st in sorted_stats[:20]:
                tg = st["target"] if st["target"] > 0 else st["actual"]
                ratio = min(100.0, (st["actual"] / tg * 100)) if tg > 0 else 100.0
                print(f"{c_name[:24]:<25} | {tg:<12,} | {st['actual']:<10,} | {ratio:.1f}%")
            if len(sorted_stats) > 20:
                print(f"... 此外还有 {len(sorted_stats)-20} 个地方法院/层级记录已成功写入 CSV 表格！")
            print("==========================================================================\n")
            
    except Exception as e:
        print(f"Error during conversion: {e}")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(base_dir)
    jsonl_path = os.path.join(project_root, "wenshu_2015mon.jsonl")
    csv_path = os.path.join(project_root, "wenshu_2015mon.csv")
    jsonl_to_csv(jsonl_path, csv_path)
