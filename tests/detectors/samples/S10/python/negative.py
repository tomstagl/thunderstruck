from .retry import retry

@retry(times=3)
def load_profile(user_id):
    return fetch_profile(user_id)
