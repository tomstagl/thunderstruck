import requests
from requests.utils import super_len


def body_size(body) -> int:
    try:
        return super_len(body)
    except requests.RequestException:
        return 0
