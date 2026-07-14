import requests
url4 = "https://account.court.gov.cn/captcha/get"
resp4 = requests.get(url4, params={"appkey":"akan"})
print("4", resp4.status_code, resp4.text[:100])

url5 = "https://account.court.gov.cn/api/captcha/get"
resp5 = requests.get(url5, params={"appkey":"akan"})
print("5", resp5.status_code, resp5.text[:100])

url6 = "https://account.court.gov.cn/captcha/getCode"
resp6 = requests.get(url6)
print("6", resp6.status_code, resp6.text[:100])
