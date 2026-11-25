const { AUTH_SERVER } = process.env;

export async function verify(token: string) {
  const res = await fetch(`${AUTH_SERVER}/verify`, {
    headers: { authorization: token },
  });
  return res.json();
}
