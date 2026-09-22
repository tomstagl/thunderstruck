import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import TRANSIENT_STATUSES

session = requests.Session()
session.mount("https://", HTTPAdapter(
    max_retries=Retry(total=3, backoff_factor=0.5, status_forcelist=TRANSIENT_STATUSES)))
