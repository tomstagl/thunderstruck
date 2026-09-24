package com.example.client;

import org.springframework.web.client.RestTemplate;

public class RecommendationClient {
    private final RestTemplate restTemplate;

    public RecommendationClient(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public String getRecommendations(String userId) {
        return restTemplate.getForObject("https://recs.example.com/{id}", String.class, userId);
    }
}

class VetsIndexLoader {
    private final org.springframework.web.reactive.function.client.WebClient webClient;
    private final com.fasterxml.jackson.databind.ObjectMapper mapper =
            new com.fasterxml.jackson.databind.ObjectMapper();

    VetsIndexLoader(org.springframework.web.reactive.function.client.WebClient webClient) {
        this.webClient = webClient;
    }

    String load() {
        java.util.List<?> vets = webClient.get().uri("http://vets-service/vets")
                .retrieve().bodyToMono(java.util.List.class).block();
        return toJson(vets);
    }

    private String toJson(Object value) {
        try {
            return mapper.writeValueAsString(value);
        } catch (com.fasterxml.jackson.core.JacksonException e) {
            return null;
        }
    }
}
