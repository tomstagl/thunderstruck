import retry from 'async-retry';
export async function load(url: string) {
  return retry(async (bail) => {
    const res = await fetch(url, { signal: AbortSignal.timeout(5000) });
    if (res.status === 404) { bail(new Error('not found')); return; }
    return res.json();
  }, { retries: 3, factor: 2, randomize: true, maxTimeout: 10_000 });
}
