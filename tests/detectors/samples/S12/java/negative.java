package com.example.client;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;

public class RetryingClient {
    private static final int MAX_RETRIES = 3;
    private final CircuitBreaker breaker;

    public RetryingClient(CircuitBreaker breaker) {
        this.breaker = breaker;
    }

    public String call() {
        return breaker.executeSupplier(this::doCall);
    }

    private String doCall() { return "ok"; }
}
