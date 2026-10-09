export async function getRelease(id: string) {
  const res = await fetch(`https://api.example.com/releases/${id}`);  // boundary: HTTP
  return res.json();
}
