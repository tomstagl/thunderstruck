def load_events(cursor, tenant):
    cursor.execute("SELECT * FROM events WHERE tenant = %s", (tenant,))
    return cursor.fetchmany(500)
