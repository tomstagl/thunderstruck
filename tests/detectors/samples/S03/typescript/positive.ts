export async function fetchPage(url: string) {
  const res = await fetch(url, { signal: AbortSignal.timeout(5_000) });
  if (res.status === 429) {
    await new Promise(r => setTimeout(r, 1000));
    return fetchPage(url);
  }
  return res;
}
