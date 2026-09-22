export async function syncAll() {
  let page = 1;
  while (true) {
    const body = await getPage(page);
    for (const item of body.items) await db.create({ data: item });
    if (!body.has_more) break;
    page += 1;
  }
}
