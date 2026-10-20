import logging

logger = logging.getLogger(__name__)


def handle(event, store):
    logger.warning("event arrived late", exc_info=True)
    try:
        store.save(event)
    except Exception:
        pass
