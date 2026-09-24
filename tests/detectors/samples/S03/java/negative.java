package com.example.client;

import java.net.http.HttpResponse;

public class RetryingClient {
    public void handle(HttpResponse<String> response) {
        if (response.statusCode() == 429 || response.statusCode() == 503) {
            response.headers().firstValue("Retry-After").ifPresent(this::retryAfter);
        }
    }

    private void retryAfter(String value) { }
}
