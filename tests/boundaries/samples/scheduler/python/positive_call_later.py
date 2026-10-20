def arm(hub, job, timeout, on_timeout):
    return hub.call_later(timeout, on_timeout, job)  # boundary: scheduler
