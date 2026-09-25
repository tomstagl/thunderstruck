import socket


def drain(connection):
    while True:
        try:
            connection.drain_events(timeout=1)
        except socket.timeout:
            pass
