export async function refresh(id: string) {
  try {
    await sync(id);
  } catch (error) {
    logger.error(`Failed to refresh ${id}`, error);
  }
}
