const queue: Job[] = [];

export function submit(job: Job, priority: "interactive" | "background") {
  if (priority === "interactive") queue.unshift(job);
  else queue.push(job);
}
