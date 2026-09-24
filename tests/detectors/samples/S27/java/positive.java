package com.example.pipeline;

import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import reactor.core.publisher.Mono;

public class OrderHandler {
    private final HttpClient httpClient = HttpClient.newHttpClient();

    public Mono<String> loadOrder(String orderId, HttpRequest request) {
        return Mono.fromSupplier(() -> {
            try {
                Thread.sleep(50);
                return httpClient.send(request, HttpResponse.BodyHandlers.ofString()).body();
            } catch (Exception e) {
                throw new IllegalStateException(e);
            }
        });
    }
}
