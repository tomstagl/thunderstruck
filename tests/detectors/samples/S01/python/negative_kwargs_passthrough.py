import requests

def get(url, **kw):
    kw.setdefault("timeout", 10)
    return requests.get(url, **kw)
