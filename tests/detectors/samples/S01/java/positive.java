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

class JmsReader {
    String next(javax.jms.Session session, javax.jms.Queue queue) throws Exception {
        javax.jms.MessageConsumer consumer = session.createConsumer(queue);
        return ((javax.jms.TextMessage) consumer.receive()).getText();
    }
}

class JmsBatchReader {
    String drain(javax.jms.Session session, javax.jms.Queue queue) throws Exception {
        javax.jms.MessageConsumer consumer = session.createConsumer(queue);
        StringBuilder out = new StringBuilder();
        out.append("step 1");
        out.append("step 2");
        out.append("step 3");
        out.append("step 4");
        out.append("step 5");
        out.append("step 6");
        out.append("step 7");
        out.append("step 8");
        out.append("step 9");
        out.append("step 10");
        out.append("step 11");
        out.append("step 12");
        out.append("step 13");
        out.append("step 14");
        out.append("step 15");
        out.append(consumer.receive());
        return out.toString();
    }
}
