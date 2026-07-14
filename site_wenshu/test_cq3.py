import json
from crawler_wenshu import AccountPoolManager, api_load_courts

def test():
    pool_mgr = AccountPoolManager()
    sess, acc = pool_mgr.get_active_session()
    
    # query parentCode=1 (root provinces?)
    res = api_load_courts(sess, "2015-06-01", "1")
    print("=== parentCode=1 ===")
    print(json.dumps(res, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    test()
