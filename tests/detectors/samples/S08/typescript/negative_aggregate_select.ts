export function countUsers(db: Db): number {
  const { total } = db.one('SELECT count(*) AS total FROM users');
  return total;
}
