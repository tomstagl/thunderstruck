import requests


def lookup(term):
    return requests.get(
        "https://api.example.com/search", params={"q": term}, timeout=5
    ).json()
