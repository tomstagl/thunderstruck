export function closeQuietly(conn: Connection) {
  try {
    conn.close();
  } catch (_err) {
    // already closed
  }
}
