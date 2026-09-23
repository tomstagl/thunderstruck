package com.example.client;

import io.github.resilience4j.retry.annotation.Retry;
import org.springframework.retry.annotation.Retryable;

public class DoublyRetriedClient {
    @Retryable(maxAttempts = 3)
    @Retry(name = "orders")
    public String call() {
        return doCall();
    }

    private String doCall() { return "ok"; }
}
