export class AsyncFifo<T> {
  private items: T[] = [];

  public async fetch(): Promise<T | void> {
    return this.items.shift();
  }
}

export async function drain(queue: AsyncFifo<Job>) {
  let job = await queue.fetch();
  while (job) job = await queue.fetch();
}
