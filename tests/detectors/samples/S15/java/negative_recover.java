package com.example.client;

import org.springframework.retry.annotation.Recover;
import org.springframework.retry.annotation.Retryable;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

public class RecommendationClient {
    private final RestTemplate restTemplate;

    public RecommendationClient(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    @Retryable(retryFor = RestClientException.class)
    public String getRecommendations(String userId) {
        return restTemplate.getForObject("https://recs.example.com/{id}", String.class, userId);
    }

    @Recover
    public String none(RestClientException e, String userId) {
        return "";
    }
}
