package com.example.pipeline;

import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public class OrderHandler {
    private final HttpClient httpClient = HttpClient.newHttpClient();

    public Mono<String> loadOrder(String orderId, HttpRequest request) {
        return Mono.fromCallable(() -> {
                    Thread.sleep(50);
                    return httpClient.send(request, HttpResponse.BodyHandlers.ofString()).body();
                })
                .subscribeOn(Schedulers.boundedElastic());
    }
}
