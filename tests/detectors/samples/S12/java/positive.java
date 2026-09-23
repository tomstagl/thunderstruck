package com.example.client;

public class RetryingClient {
    private static final int MAX_RETRIES = 3;

    public String call() {
        RuntimeException last = null;
        for (int attempt = 0; attempt < MAX_RETRIES; attempt++) {
            try {
                return doCall();
            } catch (RuntimeException e) {
                last = e;
            }
        }
        throw last;
    }

    private String doCall() { return "ok"; }
}
