def load(conn, user_id):
    orders = conn.execute("SELECT * FROM orders WHERE status = 'open'")
    user = conn.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    return user, orders
