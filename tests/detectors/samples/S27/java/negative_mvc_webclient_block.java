package com.example.web;

import java.time.Duration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@RestController
public class ProfileController {
    private final WebClient webClient;

    public ProfileController(WebClient webClient) {
        this.webClient = webClient;
    }

    @GetMapping("/profile")
    public String profile() {
        Mono<String> body = webClient.get().uri("/profile").retrieve().bodyToMono(String.class);
        return body.block(Duration.ofSeconds(2));
    }
}
