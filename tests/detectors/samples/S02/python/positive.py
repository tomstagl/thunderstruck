import requests, time

def call_with_retry(url):
    for attempt in range(5):
        r = requests.get(url, timeout=5)
        if r.ok:
            return r
        time.sleep(3)
    raise RuntimeError("give up")
