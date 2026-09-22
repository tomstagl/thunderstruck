import random, requests, time

BASE_S = 0.1
MAX_S = 20.0

def backoff_s(attempt):
    capped = min(BASE_S * 2 ** attempt, MAX_S)
    return capped * (0.5 + random.random() * 0.5)

def call_with_retry(url):
    for attempt in range(5):
        r = requests.get(url, timeout=5)
        if r.ok:
            return r
        time.sleep(backoff_s(attempt))
    raise RuntimeError("give up")
