class Worker:
    def __init__(self, queues, queue_class=None, worker_class=None):
        self.queue_class = import_queue_class(queue_class)
        self.worker_class = import_worker_class(worker_class)
        self.queues = prepare_queues(queues)

    def enqueue(self, job):
        self.queues[0].enqueue_job(job)
