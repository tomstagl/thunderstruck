export async function syncAll() {
  let page = await loadCheckpoint();
  while (true) {
    const body = await getPage(page);
    for (const item of body.items) {
      await db.upsert({ where: { id: item.id }, create: item, update: item });
    }
    await saveCheckpoint(page + 1);
    if (!body.has_more) break;
    page += 1;
  }
}
