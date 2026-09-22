const inflight = new Map<string, Promise<Release>>();

export async function getRelease(id: string) {
  const hit = cache.get(id);
  if (hit) return hit;
  const pending = inflight.get(id);
  if (pending) return pending;
  const promise = fetchRelease(id).then(v => {
    cache.set(id, v);
    inflight.delete(id);
    return v;
  });
  inflight.set(id, promise);
  return promise;
}
