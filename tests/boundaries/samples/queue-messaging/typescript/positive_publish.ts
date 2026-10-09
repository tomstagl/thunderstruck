export async function enqueue(message: unknown): Promise<void> {
  await broker.publish({ body: JSON.stringify(message) });  // boundary: queue/messaging
}
