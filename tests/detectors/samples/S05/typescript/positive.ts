export async function lookupAll(terms: string[]) {
  const out = [];
  for (const term of terms) {
    const res = await fetch(`https://api.example.com/search?q=${term}`, {
      signal: AbortSignal.timeout(5_000),
    });
    out.push(await res.json());
  }
  return out;
}
