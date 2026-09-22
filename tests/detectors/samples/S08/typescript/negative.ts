import pLimit from "p-limit";

export async function enrichAll(ids: string[]) {
  const limit = pLimit(8);
  return Promise.all(ids.map(id => limit(() => enrich(id))));
}
