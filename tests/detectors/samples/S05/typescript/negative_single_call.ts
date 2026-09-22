export async function getUser(id: string) {
  const res = await fetch(`https://api.example.com/users/${id}`, {
    signal: AbortSignal.timeout(5_000),
  });
  return res.json();
}
