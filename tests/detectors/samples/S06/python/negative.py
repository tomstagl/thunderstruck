import queue

work_queue = queue.PriorityQueue(maxsize=100)

def submit(job, priority="background"):
    rank = 0 if priority == "interactive" else 10
    work_queue.put((rank, job))
