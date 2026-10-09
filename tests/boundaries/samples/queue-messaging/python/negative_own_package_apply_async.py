# own-packages: celery
# Celery's own canvas: inside the library, `self.apply_async(` calls Celery's
# own code, so its import of itself is not a client import (#58).
from celery._state import current_app
from celery.utils.functional import maybe_list


class Signature(dict):
    def delay(self, *partial_args, **partial_kwargs):
        return self.apply_async(partial_args, partial_kwargs)
