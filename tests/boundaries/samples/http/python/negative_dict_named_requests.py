from celery.worker.state import requests


def forget(r):
    requests.pop(r.id, None)
