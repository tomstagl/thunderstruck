import requests
from requests.adapters import HTTPAdapter


def describe(message: requests.Response) -> str:
    return f"{message.status_code} {message.reason}"


def mount(session, adapter: HTTPAdapter):
    session.mount("https://", adapter)
