export interface PgModule {
  Pool: new (config?: string) => PgPool;
}

export function describe(worker: ChildProcess) {
  worker.stdout?.on('data', (data) => log(data));
  return {
    queues: Object.values(QueueName).map((name) => ({ name })),
  };
}
