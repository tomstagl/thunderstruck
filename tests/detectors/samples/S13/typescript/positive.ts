import { Pool } from 'pg';

const pool = new Pool({ max: 10 });

export async function handleRequest(id: string) {
  return pool.query('SELECT * FROM orders WHERE id = $1', [id]);
}

export async function nightlyExport() {
  return pool.query('SELECT * FROM orders');
}
