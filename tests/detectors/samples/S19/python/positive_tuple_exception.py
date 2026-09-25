def record(event):
    try:
        write_event(event)
    except (ValueError, Exception):
        pass
