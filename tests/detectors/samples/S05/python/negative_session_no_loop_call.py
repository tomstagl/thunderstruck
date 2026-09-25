import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[502, 503, 504],
              respect_retry_after_header=True)
session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=retry))

def get_user(uid):
    r = session.get(f"https://api.example.com/users/{uid}", timeout=(3, 10))
    r.raise_for_status()
    return r.json()

def names(users):
    for u in users:
        yield u["name"]
