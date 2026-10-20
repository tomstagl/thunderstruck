export async function retry(job: Job) {
  await enqueue({ type: "sync", id: job.id });
}
