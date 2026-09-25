def call(backend, func):
    retries = 0
    while True:
        try:
            return func()
        except Exception as exc:
            if backend.exception_safe_to_retry(exc) and retries < 3:
                retries += 1
                continue
            raise
