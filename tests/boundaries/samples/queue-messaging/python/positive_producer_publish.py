def send(producer, body, routing_key):
    return producer.publish(body, routing_key=routing_key, retry=True)  # boundary: queue/messaging
