import sys


def dump_request(kwargs):
    sys.stderr.write(f">>> requests.request(**{kwargs!r})\n")
