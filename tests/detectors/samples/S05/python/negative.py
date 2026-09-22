import requests
from .limiter import rate_limit

@rate_limit(calls=60, period=60)
def lookup(term):
    return requests.get(
        "https://api.example.com/search", params={"q": term}, timeout=5
    ).json()
