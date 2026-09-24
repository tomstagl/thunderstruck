package com.example.client;

import java.io.IOException;
import org.springframework.retry.annotation.Backoff;
import org.springframework.retry.annotation.Retryable;

public class RetryingClient {
    @Retryable(
        retryFor = IOException.class,
        noRetryFor = IllegalArgumentException.class,
        maxAttempts = 5,
        backoff = @Backoff(
            delay = 100,
            multiplier = 2,
            maxDelay = 5000,
            random = true
        )
    )
    public String call() throws IOException {
        return doCall();
    }

    private String doCall() throws IOException { return "ok"; }
}
