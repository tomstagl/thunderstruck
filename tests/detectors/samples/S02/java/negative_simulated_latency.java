package com.example.backend;

import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import io.github.resilience4j.retry.annotation.Retry;
import io.github.resilience4j.timelimiter.annotation.TimeLimiter;
import io.vavr.control.Try;
import java.util.concurrent.CompletableFuture;

// A demo backend next to resilience4j's @Retry. The sleeps simulate a slow
// dependency so the TimeLimiter has something to cut off. They are not the
// wait between retry attempts: resilience4j owns that, from configuration.
public class BackendService {

    @CircuitBreaker(name = "backend")
    @Retry(name = "backend")
    public String failure() {
        throw new IllegalStateException("BAM!");
    }

    @TimeLimiter(name = "backend")
    @CircuitBreaker(name = "backend", fallbackMethod = "fallback")
    public CompletableFuture<String> slowResponse() {
        Try.run(() -> Thread.sleep(5000));
        return CompletableFuture.completedFuture("Hello World from backend");
    }

    private String timeout() {
        try {
            Thread.sleep(10000);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        return "";
    }

    private CompletableFuture<String> fallback(Throwable ex) {
        return CompletableFuture.completedFuture("Recovered: " + ex);
    }
}
