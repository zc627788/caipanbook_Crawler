import json
from crawler_wenshu import AccountPoolManager, api_left_item, api_load_courts

def test():
    pool_mgr = AccountPoolManager()
    sess, acc = pool_mgr.get_active_session()
    
    conds = [{"key": "cprq", "value": "2015-06-01 TO 2015-06-01"}, {"key": "s33", "value": "重庆市"}]
    
    # 1. query s39
    res39 = api_left_item(sess, "2015-06-01", conds, "s39")
    print("=== s39 ===")
    print(json.dumps(res39, ensure_ascii=False, indent=2))
    
    # 2. query s40 directly
    res40 = api_left_item(sess, "2015-06-01", conds, "s40")
    print("=== s40 ===")
    print(json.dumps(res40, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    test()
