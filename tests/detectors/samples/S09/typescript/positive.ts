export async function getRelease(id: string) {
  const hit = cache.get(id);
  if (hit) return hit;
  const value = await fetchRelease(id);
  cache.set(id, value);
  return value;
}
