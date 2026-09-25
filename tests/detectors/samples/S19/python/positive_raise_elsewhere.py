def record(event):
    try:
        write_event(event)
    except:
        log("x")

def check(y):
    if y:
        raise
