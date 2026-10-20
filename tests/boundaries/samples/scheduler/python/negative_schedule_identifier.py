def add_periodic_task(self, schedule, sig, name=None):
    scheduled_requests.clear()
    return self._entries.setdefault(name, (schedule, sig))
