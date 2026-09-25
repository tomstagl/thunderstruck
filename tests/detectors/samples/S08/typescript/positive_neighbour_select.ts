export function load(db: Db, userId: string) {
  const orders = db.all("SELECT * FROM orders WHERE status = 'open'");
  const user = db.first('SELECT * FROM users WHERE id = ?', [userId]);
  return { user, orders };
}
