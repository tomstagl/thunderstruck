export function group(rows: Row[]) {
  const m = new Map();
  for (const r of rows) m.set(r.k, r);
  return m;
}
