export async function callWithRetry(url: string) {
  for (let attempt = 0; attempt < 5; attempt++) {
    const res = await fetch(url, { signal: AbortSignal.timeout(5_000) });
    if (res.ok) return res;
    await new Promise(r => setTimeout(r, 3000));
  }
  throw new Error("give up");
}
