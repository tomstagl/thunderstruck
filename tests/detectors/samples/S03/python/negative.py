import requests, time

def fetch_page(url):
    r = requests.get(url, timeout=5)
    if r.status_code == 429:
        retry_after = r.headers.get("Retry-After")
        time.sleep(int(retry_after) if retry_after else 60)
        return fetch_page(url)
    return r
