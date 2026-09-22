const BASE_MS = 100;
const MAX_MS = 20_000;

function backoffMs(attempt: number): number {
  const capped = Math.min(BASE_MS * Math.pow(2, attempt), MAX_MS);
  return Math.round(capped * (0.5 + Math.random() * 0.5));
}

export async function callWithRetry(url: string) {
  for (let attempt = 0; attempt < 5; attempt++) {
    const res = await fetch(url, { signal: AbortSignal.timeout(5_000) });
    if (res.ok) return res;
    await new Promise(r => setTimeout(r, backoffMs(attempt)));
  }
  throw new Error("give up");
}
