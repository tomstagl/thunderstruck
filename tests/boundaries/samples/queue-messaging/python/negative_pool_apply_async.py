from celery import signals


def run(pool, fn, args):
    return pool.apply_async(fn, args)
