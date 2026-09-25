import logging
log = logging.getLogger(__name__)

def handle_all(items):
    for entry in range(len(items)):
        try:
            handle(items[entry])
        except Exception:
            log.warning("skipping item %d", entry)
