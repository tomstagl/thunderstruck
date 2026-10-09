import logging
import time

logger = logging.getLogger(__name__)


class Backend:
    max_retries = 3

    def ensure_retryable(self, func):
        retries = 0
        while True:
            try:
                return func()
            except Exception as exc:
                if self.exception_safe_to_retry(exc):
                    if retries < self.max_retries:
                        retries += 1
                        sleep_amount = min(2 ** retries, 30)
                        delay = sleep_amount / 1000
                        logger.warning("Retrying %s more times.", self.max_retries - retries)
                        try:
                            self.on_retryable_error(exc)
                        except Exception:
                            logger.exception("hook failed; continuing retry loop")
                        time.sleep(delay)
                    else:
                        raise
                else:
                    raise
