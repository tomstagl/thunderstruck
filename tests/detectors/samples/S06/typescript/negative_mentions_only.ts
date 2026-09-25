import { QueueBase } from './queue-base';

export interface ParentOptions {
  id: string;
  queue: string;
}

export const summary = 'A fast, Redis-based queue for Node.';

export function parentKey(opts: ParentOptions): string {
  return `${opts.queue}:${opts.id}`;
}
