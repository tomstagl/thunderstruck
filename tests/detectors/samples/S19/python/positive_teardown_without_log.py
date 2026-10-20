def finish(conn):
    try:
        conn.close()
    except Exception:
        pass
