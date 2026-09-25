import requests

def ids(clients):
    out = []
    for c in clients:
        cid = c.client_config.get("id")
        out.append(cid)
    return out

def status():
    return requests.get("https://api.example.com/status", timeout=5).json()
