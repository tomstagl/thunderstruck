def record(event):
    try:
        write_event(event)
    except Exception:
        pass
