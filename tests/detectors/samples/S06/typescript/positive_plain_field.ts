import PQueue from 'p-queue';

export class Svc {
  queue = new PQueue({ concurrency: 2 });
}
