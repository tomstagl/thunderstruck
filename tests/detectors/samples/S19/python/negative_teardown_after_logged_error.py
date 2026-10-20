import logging

logger = logging.getLogger(__name__)


class Consumer:
    def on_connection_error(self, exc):
        logger.warning("connection lost, reconnecting", exc_info=True)
        try:
            self.connection.collect(socket_timeout=2)
        except Exception:
            pass
        self.restart()
