def load(conn, ids):
    return conn.execute("""
        SELECT * FROM users
        WHERE id = ANY(%s)
    """, (ids,))
