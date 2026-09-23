package com.example.client;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.decorators.Decorators;
import org.springframework.web.client.RestTemplate;

public class RecommendationClient {
    private final RestTemplate restTemplate;
    private final CircuitBreaker breaker;

    public RecommendationClient(RestTemplate restTemplate, CircuitBreaker breaker) {
        this.restTemplate = restTemplate;
        this.breaker = breaker;
    }

    public String getRecommendations(String userId) {
        return Decorators.ofSupplier(() -> callUpstream(userId))
                .withCircuitBreaker(breaker)
                .withFallback(t -> defaultRecommendations())
                .get();
    }

    private String callUpstream(String userId) {
        return restTemplate.getForObject("https://recs.example.com/{id}", String.class, userId);
    }

    private String defaultRecommendations() { return "default"; }
}
