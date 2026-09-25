export function messagesSince(db: Db, since: string) {
  return db.all(
    `SELECT * FROM messages_binary
       WHERE timestamp > ?
       ORDER BY timestamp`,
    [since],
  );
}
