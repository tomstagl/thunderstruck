from time import sleep


def shutdown_nodes(nodes, retry=None, **kwargs):
    pending = set(nodes)
    while pending:
        pending = {n for n in pending if n.alive()}
        if pending:
            sleep(float(retry))
