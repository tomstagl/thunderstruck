import { z } from 'zod';

export const QUEUE_EVENT_SUFFIX = ':qe';
export const IWorker = 'IWorker';
export const QueueNameSchema = z.enum(['thumbnails', 'search']);
const WORKER_TYPES = new Set(['api', 'microservices']);
export const defaultQueueOptions = { concurrency: 1 };
export const SvgQueue = (props: { size: number }) => props.size;
