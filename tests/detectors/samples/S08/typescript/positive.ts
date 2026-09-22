export async function enrichAll(ids: string[]) {
  return Promise.all(ids.map(id => enrich(id)));
}
