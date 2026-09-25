export async function withReconnect<T>(fn: () => Promise<T>, maxRetries = 5): Promise<T> {
  for (let attempt = 1; ; attempt++) {
    try {
      return await fn();
    } catch (err) {
      if (isNotConnectionError(err as Error) || attempt >= maxRetries) throw err;
      await delay(1000 * attempt);
    }
  }
}
