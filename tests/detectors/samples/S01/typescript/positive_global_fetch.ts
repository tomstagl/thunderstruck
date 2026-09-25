export async function latest(url: string) {
  const res = await globalThis.fetch(url);
  return res.json();
}
