package com.example.client;

import java.util.concurrent.ThreadLocalRandom;

public class RetryingClient {
    private static final long BASE_MS = 100;
    private static final long MAX_MS = 5000;

    public String call() throws InterruptedException {
        for (int attempt = 0; attempt < 3; attempt++) {
            try {
                return doCall();
            } catch (Exception e) {
                long backoff = Math.min(MAX_MS, BASE_MS * (1L << attempt));
                long jittered = ThreadLocalRandom.current().nextLong(backoff);
                Thread.sleep(jittered);
            }
        }
        throw new IllegalStateException("exhausted retries");
    }

    private String doCall() { return "ok"; }
}
