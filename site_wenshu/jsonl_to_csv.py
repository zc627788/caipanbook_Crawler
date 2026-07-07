import json
import csv
import sys
import os

def jsonl_to_csv(jsonl_path, csv_path):
    if not os.path.exists(jsonl_path):
        print(f"Error: {jsonl_path} does not exist.")
        return

    headers = ["title", "court", "case_no", "content", "date", "type_code", "proc_code", "doc_id", "extra", "source", "flag"]
    
    # 建立数字 key 到英文 header 的映射
    field_map = {
        "1":      "title",
        "2":      "court",
        "7":      "case_no",
        "9":      "type_code",
        "10":     "proc_code",
        "26":     "content",
        "31":     "date",
        "32":     "extra",
        "43":     "source",
        "44":     "flag",
        "rowkey": "doc_id",
    }
    
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f_in, \
             open(csv_path, "w", encoding="utf-8-sig", newline="") as f_out:
            
            # 强制所有字段使用双引号包裹，防止标题中的分号或正文里的符号干扰 Excel 列对齐
            writer = csv.DictWriter(f_out, fieldnames=headers, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            
            count = 0
            for line in f_in:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    # 将所有 raw key 转换为标准 header key
                    norm_data = {}
                    for k, v in data.items():
                        norm_key = field_map.get(k, k)
                        norm_data[norm_key] = v
                    
                    row = {}
                    for h in headers:
                        val = norm_data.get(h, "")
                        if isinstance(val, str):
                            # 将换行符替换为普通空格，确保在文本编辑器中严格单行对齐
                            val = val.replace("\r", "").replace("\n", " ")
                        row[h] = val
                    writer.writerow(row)
                    count += 1
                except Exception as e:
                    print(f"Skipping bad line: {e}")
            
            print(f"Successfully converted {count} rows from {jsonl_path} to {csv_path}")
            
    except Exception as e:
        print(f"Error during conversion: {e}")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    jsonl_path = os.path.join(base_dir, "wenshu_2025july.jsonl")
    csv_path = os.path.join(base_dir, "wenshu_2025july.csv")
    jsonl_to_csv(jsonl_path, csv_path)
