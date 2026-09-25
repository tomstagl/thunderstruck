class Queue:
    def __init__(self, name="default", connection=None):
        if not connection:
            raise TypeError("Queue() missing 1 required positional argument: 'connection'")
        self.name = name
