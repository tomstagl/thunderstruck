export class ThrottleService {
  private seen: Map<string, number> = new Map();

  record(key: string) {
    this.seen.set(key, Date.now());
  }
}
