export async function all() {
  const a = await fetch("http://localhost:3000/v1/x");
  const b = await fetch("http://127.0.0.2/v1/x");
  const c = await fetch("https://example.com/v1/x");
  const d = await fetch("https://svc.test/v1/x");
  const e = await fetch("https://json-schema.org/draft/2020-12/schema");
  const f = await fetch(`https://${HOST}/v1/x`);
  const g = await fetch("https://{{ .Values.host }}/v1/x");
  if (!a.ok) throw new Error("see https://docs.python.org/3/library/json.html");
  return [await b.json(), c.status, d.ok, e.headers, f.ok, g.ok];
}
