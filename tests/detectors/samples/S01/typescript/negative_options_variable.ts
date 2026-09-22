export async function getUser(id: string) {
  const init = { signal: AbortSignal.timeout(5_000) };
  const res = await fetch(`https://api.example.com/users/${id}`, init);
  return res.json();
}
