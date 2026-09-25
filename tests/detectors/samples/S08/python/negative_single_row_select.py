def load(conn, user_id):
    row = conn.execute("SELECT id, name FROM users WHERE id = %s", (user_id,)).fetchone()
    n = conn.execute("SELECT count(*) FROM users").fetchone()
    return row, n
