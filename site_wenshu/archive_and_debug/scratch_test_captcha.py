import requests
url = "https://account.court.gov.cn/captcha/getImg"
resp = requests.post(url, data={"appkey":"akan"})
print("1", resp.status_code, resp.text[:100])

url2 = "https://account.court.gov.cn/captcha/get"
resp2 = requests.post(url2, data={"appkey":"akan"})
print("2", resp2.status_code, resp2.text[:100])

url3 = "https://account.court.gov.cn/api/captcha/getImg"
resp3 = requests.post(url3, data={"appkey":"akan"})
print("3", resp3.status_code, resp3.text[:100])
