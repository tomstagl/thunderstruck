import requests


def kind_of(message):
    if isinstance(message, requests.PreparedRequest):
        return "request"
    elif isinstance(message, requests.Response):
        return "response"
    else:
        raise TypeError(f"Unexpected message type: {type(message).__name__}")


def enqueue_ready(pipe, job):
    pipe.execute()
    assert job.rate_limit_concurrency
    return job


def latest(session, url):
    response = requests.get(url, timeout=5)
    return version.parse(response.json()["tag_name"])
