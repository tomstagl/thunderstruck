package com.example.client;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.sql.Connection;
import java.sql.DriverManager;
import java.util.concurrent.CompletableFuture;
import okhttp3.OkHttpClient;

public class UserClient {
    private final HttpClient client = HttpClient.newBuilder().build();
    private final OkHttpClient okHttp = new OkHttpClient.Builder().build();

    public String fetchUser(String userId) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.example.com/users/" + userId))
                .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString()).body();
    }

    public Connection openConnection() throws Exception {
        return DriverManager.getConnection("jdbc:postgresql://db/app");
    }

    public String fetchAsync(HttpRequest request) throws Exception {
        CompletableFuture<HttpResponse<String>> future =
                client.sendAsync(request, HttpResponse.BodyHandlers.ofString());
        return future.get().body();
    }
}

class SpringClients {
    private final org.springframework.web.client.RestTemplate rest =
            new org.springframework.web.client.RestTemplate();
    private final org.springframework.web.reactive.function.client.WebClient web =
            org.springframework.web.reactive.function.client.WebClient.create("https://api.example.com");
}
