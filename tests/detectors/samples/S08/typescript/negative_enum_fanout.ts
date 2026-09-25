export enum QueueName {
  Thumbnails = 'thumbnails',
  Search = 'search',
}

export async function statusAll() {
  return Promise.all(Object.values(QueueName).map((name) => getStatus(name)));
}
