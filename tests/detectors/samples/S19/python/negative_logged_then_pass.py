import logging

logger = logging.getLogger(__name__)


def collect(callbacks, data):
    out = {}
    for callback in callbacks:
        try:
            out.update(callback(data))
        except Exception as e:
            logger.warning(f"callback {callback} failed: {e}")
            pass
    return out
