import requests
from eventlet import Timeout


def crawl(url):
    with Timeout(5, False):
        try:
            response = requests.get(url)
        except requests.RequestException:
            return None
    return response.text
