export class DnsCache {
  readonly #cache = new Map<string, Entry[]>();
  readonly #pending = new Map<string, Promise<Entry[]>>();

  async lookup(hostname: string): Promise<Entry[]> {
    const hit = this.#cache.get(hostname);
    if (hit) return hit;
    let query = this.#pending.get(hostname);
    if (!query) {
      query = resolve(hostname).finally(() => this.#pending.delete(hostname));
      this.#pending.set(hostname, query);
    }
    const entries = await query;
    this.#cache.set(hostname, entries);
    return entries;
  }
}
