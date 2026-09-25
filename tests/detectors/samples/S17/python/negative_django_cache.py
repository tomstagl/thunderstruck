from django.core.cache import cache


def remember_release(release):
    cache.set("latest_release", release, None)


class Loader:
    def __init__(self):
        self._cache = import_module("django.core.cache")
        self._backend_cache = None
