export function getPasswordHash(db: Db): string | undefined {
  const row = db.first('SELECT extra_data FROM auth WHERE method = ?', ['password']);
  return row?.extra_data;
}
