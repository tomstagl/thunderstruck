import queue

work_queue = queue.Queue(maxsize=100)

def submit(job):
    work_queue.put(job)
