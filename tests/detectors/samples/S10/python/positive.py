from .retry import retry

@retry(times=3)
def load_profile(user_id):
    for attempt in range(3):
        r = fetch_profile(user_id)
        if r.ok:
            return r
    raise RuntimeError("failed")
