export function load(db: Db, ids: string[]) {
  return db.all(`
    SELECT * FROM users
    WHERE id = ANY($1)
  `, [ids]);
}
