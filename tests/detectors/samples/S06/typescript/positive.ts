const queue: Job[] = [];

export function submit(job: Job) {
  queue.push(job);
}
