import socket


def wait_for_result(result, max_retries=10):
    for i in range(max_retries):
        try:
            return result.get(timeout=1)
        except (socket.timeout, TimeoutError):
            continue
    raise AssertionError("result never arrived")
