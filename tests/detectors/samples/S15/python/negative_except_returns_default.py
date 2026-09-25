import requests


def latest_feed(url):
    try:
        response = requests.get(url, timeout=3)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        return {"error": str(exc), "items": []}
    return response.json()
