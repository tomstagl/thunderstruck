export type RequestRetryEvent = {
  requestId: string;
  retryCount: number;
  delay: number;
};

export interface RetryOptions {
  maxRetries?: number;
}

export interface QueueEvents {
  'retries-exhausted': (args: { jobId: string }) => void;
}
