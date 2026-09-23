package com.example.client;

import com.zaxxer.hikari.HikariConfig;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.sql.Connection;
import java.sql.DriverManager;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import okhttp3.OkHttpClient;

public class UserClient {
    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();
    private final OkHttpClient okHttp = new OkHttpClient.Builder()
            .callTimeout(Duration.ofSeconds(10))
            .build();

    public String fetchUser(String userId) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.example.com/users/" + userId))
                .timeout(Duration.ofSeconds(5))
                .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString()).body();
    }

    public Connection openConnection() throws Exception {
        DriverManager.setLoginTimeout(3);
        return DriverManager.getConnection("jdbc:postgresql://db/app");
    }

    public HikariConfig poolConfig() {
        HikariConfig config = new HikariConfig();
        config.setConnectionTimeout(3000);
        return config;
    }

    public String fetchAsync(CompletableFuture<HttpResponse<String>> future) throws Exception {
        return future.get(5, TimeUnit.SECONDS).body();
    }
}

class SpringClients {
    private final org.springframework.web.client.RestTemplate rest = restTemplate();
    private final org.springframework.web.reactive.function.client.WebClient web =
            org.springframework.web.reactive.function.client.WebClient.builder()
                    .clientConnector(new org.springframework.http.client.reactive.ReactorClientHttpConnector(
                            reactor.netty.http.client.HttpClient.create()
                                    .responseTimeout(java.time.Duration.ofSeconds(5))))
                    .build();

    private static org.springframework.web.client.RestTemplate restTemplate() {
        org.springframework.http.client.SimpleClientHttpRequestFactory factory =
                new org.springframework.http.client.SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(2000);
        factory.setReadTimeout(5000);
        return new org.springframework.web.client.RestTemplate(factory);
    }
}

class JmsReader {
    String next(javax.jms.Session session, javax.jms.Queue queue) throws Exception {
        javax.jms.MessageConsumer consumer = session.createConsumer(queue);
        return ((javax.jms.TextMessage) consumer.receive(5000)).getText();
    }
}
