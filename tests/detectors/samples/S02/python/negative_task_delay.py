from celery import shared_task


@shared_task(bind=True, max_retries=3)
def unlock(self, callback, results):
    if all(r.ready() for r in results):
        callback.delay([r.get() for r in results])
    else:
        raise self.retry(countdown=1)


def delay(*args, **kwargs):
    return unlock.apply_async(args, kwargs)
