package com.example.listener;

import org.springframework.util.backoff.BackOffExecution;

final class RedeliveryUtils {
    private RedeliveryUtils() { }

    static void redeliver(Runnable listener, BackOffExecution execution, boolean retryable) {
        long nextBackOff = execution.nextBackOff();
        while (retryable && nextBackOff != BackOffExecution.STOP) {
            if (Thread.currentThread().isInterrupted()) {
                throw new IllegalStateException("Container stopped during retries");
            }
            try {
                listener.run();
                return;
            } catch (RuntimeException e) {
                nextBackOff = execution.nextBackOff();
            }
        }
    }
}
