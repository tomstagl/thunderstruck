from time import sleep


def flush_pipes(procs):
    while procs:
        try:
            readable = select_ready(procs)
        except InterruptedError:
            continue
        if not readable:
            break
        for fd in readable:
            procs[fd].recv()
        sleep(0)
