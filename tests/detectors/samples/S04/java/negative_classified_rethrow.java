package com.example.client;

import java.io.IOException;

public class ClassifiedRetry {
    public String call(int max) throws Exception {
        for (int attempt = 1; attempt <= max; attempt++) {
            try {
                return doCall();
            } catch (Exception e) {
                if (!isRetryable(e) || attempt == max) {
                    throw e;
                }
            }
        }
        return null;
    }

    public String callSpecific(int max) throws Exception {
        for (int attempt = 1; attempt <= max; attempt++) {
            try {
                return doCall();
            } catch (IOException e) {
                if (attempt == max) throw e;
            } catch (Exception e) {
                throw new IllegalStateException("non-transient failure on attempt " + attempt, e);
            }
        }
        return null;
    }

    public void runOnce() throws Exception {
        try {
            doCall();
        } catch (Exception e) {
            System.err.println("Permanent failure, will not retry: " + e);
            throw e;
        }
    }

    private boolean isRetryable(Exception e) { return e instanceof IOException; }
    private String doCall() throws IOException { return "ok"; }
}
