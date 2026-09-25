import logging

logger = logging.getLogger(__name__)


def notify(hook, exc):
    try:
        hook(exc)
    except Exception:
        logger.exception("hook failed; continuing retry loop")
