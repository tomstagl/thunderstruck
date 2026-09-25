import time

MAX_RETRIES = 5


def push(job):
    for attempt in range(MAX_RETRIES):
        try:
            return send(job)
        except SendError:
            time.sleep(1)
    raise RuntimeError("gave up")
