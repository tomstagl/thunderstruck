export async function save(item: Item) {
  await db.release.create({ data: item });  // boundary: database
}
