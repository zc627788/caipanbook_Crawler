import requests

url = "https://account.court.gov.cn/api/login"
headers = {
    "accept": "*/*",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    "x-requested-with": "XMLHttpRequest"
}

# Payload from the user's fetch
data = "username=63-9568348610&password=pDpOkRy%252FMnNWhSKlri1srjsI8ZA9cj%252FQIXS3A4mDeZYvLA8AL7e7ZfSX8t9WPvgc5y%252BrBKcXx3RmCWCsF3BMasZzqCU%252FMUpXOi%252FHFLzBUJvfBeXfCqmEeP3VdUc6kD8HO%252F%252BIomZm1d3FeucJZWw%252BO7XQU6dMtM5WYZfx0X57psBKDGaNeUBdcXoC%252F2AJeNqnQeG0EJxzgnK5jk1aeTf8udAr0cDxwzIYkUHNdfuY5bR1euoBO0SaldohppcBt1q7pT7hYCqU52jT6fjFurp%252FL36I7Z2o%252FAk2TJ4new2zXAHs%252BmOXNGolm5lI5k%252FoCsXN%252BiPftqczaGt4gshfk1gGOw%253D%253D&bizToken=92cb90e1-6176-4c7a-ac6d-de7aaf86b258&imgVerifyToken=92cb90e1-6176-4c7a-ac6d-de7aaf86b258&appDomain=wenshu.court.gov.cn"

print("Sending user's exact payload...")
resp = requests.post(url, headers=headers, data=data)
print(resp.status_code, resp.text)
