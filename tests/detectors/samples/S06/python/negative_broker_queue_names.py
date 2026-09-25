from kombu import Exchange, Queue

from .worker import WorkController

worker_logger = "celery.worker"


def default_queues(conf):
    return [Queue(conf.task_default_queue, Exchange(conf.task_default_exchange))]


def start(app):
    worker = WorkController(app, pool="prefork")
    return worker.start()
