package com.example.client;
import io.github.resilience4j.retry.annotation.Retry;
import org.springframework.retry.annotation.Retryable;
public class Clients {
    @Retryable(maxAttempts = 3)
    public String callA() { return a(); }

    @Retry(name = "b")
    public String callB() { return b(); }

    private String a() { return "a"; }
    private String b() { return "b"; }
}
