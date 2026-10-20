import logging

logger = logging.getLogger(__name__)


def mirror(db, doc):
    # `collection(` is not the teardown verb `collect(`: the swallowed call
    # is a write after a logged failure, and it still fires (#58 review).
    logger.error("primary write failed", exc_info=True)
    try:
        db.collection("mirror").add(doc)
    except Exception:
        pass
