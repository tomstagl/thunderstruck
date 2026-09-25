export async function importOrders(rows: Row[]) {
  for (const row of rows) {
    await Order.create({ externalId: row.id, total: row.total });
  }
}
