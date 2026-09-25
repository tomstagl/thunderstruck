requests = {}


def forget(request_id):
    requests.pop(request_id, None)
    requests.clear()
