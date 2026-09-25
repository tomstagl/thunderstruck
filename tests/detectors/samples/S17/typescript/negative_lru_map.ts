export class SearchService {
  private embeddingCache = new LRUMap<string, string>(100);

  async embed(query: string) {
    let embedding = this.embeddingCache.get(query);
    if (!embedding) {
      embedding = await encode(query);
      this.embeddingCache.set(query, embedding);
    }
    return embedding;
  }
}
