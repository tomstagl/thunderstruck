// Bare hosts with no path and no API name, in a file that requests and reads.
const FOOTER = ["https://news-site.internal", "https://social.internal/"];

export async function load(url: string) {
  const res = await fetch(url);
  return { links: FOOTER, body: await res.json(), ok: res.ok };
}
