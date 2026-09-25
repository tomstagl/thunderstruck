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

class LoopInsideRetryable {
    @org.springframework.retry.annotation.Retryable(maxAttempts = 3)
    public String call() {
        for (int attempt = 0; attempt < 3; attempt++) {
            try {
                return doCall();
            } catch (RuntimeException e) {
                if (attempt == 2) {
                    throw e;
                }
            }
        }
        return null;
    }

    private String doCall() { return "ok"; }
}

class TemplateInsideResilience4j {
    private final org.springframework.retry.support.RetryTemplate retryTemplate;

    TemplateInsideResilience4j(org.springframework.retry.support.RetryTemplate retryTemplate) {
        this.retryTemplate = retryTemplate;
    }

    @io.github.resilience4j.retry.annotation.Retry(name = "orders")
    public String call() {
        return retryTemplate.execute(ctx -> doCall());
    }

    private String doCall() { return "ok"; }
}

class DefaultFeignClient {
    // Feign's Retryer.Default retries up to 5 times: a layer nobody wrote
    PaymentsApi payments() {
        return feign.Feign.builder()
            .target(PaymentsApi.class, "https://payments");
    }
}
