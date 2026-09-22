def get_release(release_id):
    hit = cache.get(release_id)
    if hit:
        return hit
    value = fetch_release(release_id)
    cache[release_id] = value
    return value
