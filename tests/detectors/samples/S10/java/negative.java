package com.example.client;

public class SingleLayerClient {
    public String call() {
        for (int attempt = 0; attempt < 3; attempt++) {
            try {
                return sdkCall();
            } catch (RuntimeException e) {
                if (attempt == 2) {
                    throw e;
                }
            }
        }
        throw new IllegalStateException("exhausted");
    }

    private String sdkCall() {
        return "ok";
    }
}
