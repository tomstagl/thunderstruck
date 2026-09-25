def publish(producer, event, buffer):
    try:
        producer.publish(event)
    except Exception:
        if not buffer:
            raise
        buffer.append(event)

def send(event, retry=False):
    return event
