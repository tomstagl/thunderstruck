import requests
from requests.auth import AuthBase
from urllib3.util import SKIP_HEADER


class TokenAuth(AuthBase):
    def __call__(self, r: requests.PreparedRequest) -> requests.PreparedRequest:
        for name in ("Authorization", SKIP_HEADER):
            r.headers.pop(name, None)
        return r
