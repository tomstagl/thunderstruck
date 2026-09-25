export function group(rows: Row[]) {
  const m = new Map();
  for (const r of rows) m.set(r.k, r);
  return m;
}

export async function download(ids: string[], repo: AssetRepository) {
  const assets = await repo.getByIds(ids);
  const assetMap = new Map(assets.map((asset) => [asset.id, asset]));
  return ids.map((id) => assetMap.get(id));
}

export function peopleOf(faces: Face[], merged: Map<string, string[]> = new Map()) {
  const people: Map<string, Person> = new Map();
  for (const face of faces) people.set(face.personId, face.person);
  return { people, merged };
}

export function empty() {
  return new Map();
}
