import requests

def save(payload):
    max_retries = 3
    for _ in range(max_retries):
        try:
            return post("/save", payload)
        except (requests.ConnectionError, requests.Timeout):
            continue
    raise RuntimeError("failed")
