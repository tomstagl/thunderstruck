export async function fetchPage(url: string) {
  const res = await fetch(url, { signal: AbortSignal.timeout(5_000) });
  if (res.status === 429) {
    const header = res.headers.get("Retry-After");
    const waitMs = header ? Number(header) * 1000 : 60_000;
    await new Promise(r => setTimeout(r, waitMs));
    return fetchPage(url);
  }
  return res;
}
