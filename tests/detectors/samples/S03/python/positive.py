import requests, time

def fetch_page(url):
    r = requests.get(url, timeout=5)
    if r.status_code == 429:
        time.sleep(1)
        return fetch_page(url)
    return r
