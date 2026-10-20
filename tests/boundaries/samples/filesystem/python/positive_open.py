def read_pid(path):
    with open(path) as fh:  # boundary: filesystem
        return int(fh.read())
