package com.example.client;

import java.io.IOException;
import org.springframework.retry.annotation.Retryable;

public class RetryingClient {
    public String call() throws IOException {
        for (int attempt = 0; attempt < 3; attempt++) {
            try {
                return doCall();
            } catch (IOException e) {
                if (!isTransient(e)) {
                    throw e;
                }
            }
        }
        throw new IllegalStateException("exhausted retries");
    }

    @Retryable(retryFor = IOException.class, maxAttempts = 3)
    public String callAnnotated() throws IOException {
        return doCall();
    }

    private boolean isTransient(IOException e) { return true; }
    private String doCall() throws IOException { return "ok"; }
}
