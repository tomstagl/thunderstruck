const queue: Array<() => Promise<unknown>> = [];

export function submit(job: () => Promise<unknown>) {
  queue.push(job);
}
