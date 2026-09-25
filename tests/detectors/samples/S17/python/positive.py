_user_cache = {}


def get_user(user_id):
    if user_id not in _user_cache:
        _user_cache[user_id] = load_user(user_id)
    return _user_cache[user_id]
