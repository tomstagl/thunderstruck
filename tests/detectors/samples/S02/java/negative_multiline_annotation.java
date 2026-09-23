package com.example.client;

import org.springframework.retry.annotation.Backoff;
import org.springframework.retry.annotation.Retryable;

public class RetryingClient {
    @Retryable(
        maxAttempts = 3,
        backoff = @Backoff(delay = 100, multiplier = 2, maxDelay = 5000, random = true)
    )
    public String call() {
        return doCall();
    }

    private String doCall() { return "ok"; }
}
