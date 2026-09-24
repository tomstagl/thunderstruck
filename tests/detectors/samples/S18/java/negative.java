package com.example.orders;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class OrderService {
    private final HttpClient client = HttpClient.newHttpClient();

    public String placeOrder(String payload) throws Exception {
        if (payload == null || payload.isBlank()) {
            throw new IllegalArgumentException("payload required");
        }
        HttpRequest request = HttpRequest.newBuilder(URI.create("https://pricing.example.com")).build();
        return client.send(request, HttpResponse.BodyHandlers.ofString()).body();
    }
}
