class Request:
    def execute(self, loglevel=None):
        """Select a subset of queues and run the task."""
        return self.run(loglevel)
