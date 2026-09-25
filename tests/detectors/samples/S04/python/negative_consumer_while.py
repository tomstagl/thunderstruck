import logging
log = logging.getLogger(__name__)

def consume(q):
    while True:
        msg = q.get()
        try:
            handle(msg)
        except Exception:
            log.exception("handler failed for %r", msg)
