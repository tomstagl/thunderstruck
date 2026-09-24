package com.example.client;

import java.time.Duration;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

public class ProductClient {
    private final WebClient client = WebClient.create("https://api.example.com");

    public Mono<String> product(String id) {
        return client.get()
                .uri(builder -> builder.path("/products/{id}")
                        .queryParam("expand", "prices")
                        .queryParam("locale", "en")
                        .build(id))
                .header("X-Client", "catalog")
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .onStatus(HttpStatusCode::isError, response -> Mono.error(new IllegalStateException()))
                .bodyToMono(String.class)
                .timeout(Duration.ofSeconds(3));
    }
}
