import json
from crawler_wenshu import AccountPoolManager, api_load_courts

def test():
    pool_mgr = AccountPoolManager()
    sess, acc = pool_mgr.get_active_session()
    
    # Try different parentCodes
    for code in ["110", "100", "M00", "5000", "500"]:
        print(f"=== {code} ===")
        res = api_load_courts(sess, "2015-06-01", code)
        print(json.dumps(res, ensure_ascii=False))

if __name__ == "__main__":
    test()
