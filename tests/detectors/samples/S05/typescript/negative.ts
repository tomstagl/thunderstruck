import { rateLimiter } from "./limiter";

export async function lookup(term: string) {
  await rateLimiter.acquire();
  const res = await fetch(`https://api.example.com/search?q=${term}`, {
    signal: AbortSignal.timeout(5_000),
  });
  return res.json();
}
