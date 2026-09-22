def record(event):
    try:
        write_event(event)
    except Exception:
        log.exception("failed to write event")
        raise
