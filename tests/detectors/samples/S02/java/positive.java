package com.example.client;

import org.springframework.retry.annotation.Retryable;

public class RetryingClient {
    public String call() throws InterruptedException {
        for (int attempt = 0; attempt < 3; attempt++) {
            try {
                return doCall();
            } catch (Exception e) {
                Thread.sleep(2000);
            }
        }
        throw new IllegalStateException("exhausted retries");
    }

    @Retryable(maxAttempts = 3)
    public String callAnnotated() {
        return doCall();
    }

    private String doCall() { return "ok"; }
}
