import json
from crawler_wenshu import AccountPoolManager, api_left_item

def test():
    pool_mgr = AccountPoolManager()
    sess, acc = pool_mgr.get_active_session()
    if not sess:
        print("No session")
        return
    
    conds = [{"key": "cprq", "value": "2015-06-01 TO 2015-06-01"}, {"key": "s33", "value": "重庆市"}]
    res = api_left_item(sess, "2015-06-01", conds, "s39,s40")
    print(json.dumps(res, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    test()
