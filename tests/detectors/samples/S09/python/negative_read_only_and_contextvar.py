from contextvars import ContextVar

from django.core.cache import cache

query_cache = ContextVar("query_cache", default=None)


def latest_release():
    return cache.get("latest_release")


def object_types():
    local = query_cache.get()
    return local["object_types"] if local is not None else None


def get_cached_value(instance, default=None):
    return instance.__dict__.get("value", default)
