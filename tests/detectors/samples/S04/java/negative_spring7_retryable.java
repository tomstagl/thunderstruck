package com.example.client;

import java.io.IOException;
import org.springframework.resilience.annotation.Retryable;

public class RetryingClient {
    @Retryable(includes = IOException.class, maxAttempts = 4, delay = 100, jitter = 50, multiplier = 2, maxDelay = 2000)
    public String call() throws IOException {
        return doCall();
    }

    private String doCall() throws IOException { return "ok"; }
}
