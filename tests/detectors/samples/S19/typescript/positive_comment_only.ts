export async function warm(key: string) {
  try {
    await cache.load(key);
  } catch (e) {
    // best effort: the cache is rebuilt
    // on the next request anyway
  }
}
