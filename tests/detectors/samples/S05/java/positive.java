package com.example.client;

import java.util.List;
import org.springframework.web.client.RestTemplate;

public class BulkClient {
    private final RestTemplate restTemplate;

    public BulkClient(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public void fetchAll(List<String> ids) {
        for (String id : ids) {
            restTemplate.getForObject("https://api.example.com/items/{id}", String.class, id);
        }
    }
}
