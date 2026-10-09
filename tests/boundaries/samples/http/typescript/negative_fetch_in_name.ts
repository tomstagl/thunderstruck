export async function batch(ids: string[]) {
  return Promise.all(ids.map(id => fetchRelease(id)));
}
