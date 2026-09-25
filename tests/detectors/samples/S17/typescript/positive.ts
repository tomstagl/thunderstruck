const cache = new Map<string, User>();
export async function getUser(id: string) { cache.set(id, await load(id)); }
