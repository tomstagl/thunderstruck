import requests

def lookup_all(terms):
    out = []
    for term in terms:
        out.append(requests.get(
            "https://api.example.com/search", params={"q": term}, timeout=5
        ).json())
    return out
