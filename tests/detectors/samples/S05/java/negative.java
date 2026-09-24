package com.example.client;

import io.github.bucket4j.Bucket;
import java.util.List;
import org.springframework.web.client.RestTemplate;

public class BulkClient {
    private final RestTemplate restTemplate;
    private final Bucket bucket;

    public BulkClient(RestTemplate restTemplate, Bucket bucket) {
        this.restTemplate = restTemplate;
        this.bucket = bucket;
    }

    public void fetchAll(List<String> ids) throws InterruptedException {
        for (String id : ids) {
            bucket.asBlocking().consume(1);
            restTemplate.getForObject("https://api.example.com/items/{id}", String.class, id);
        }
    }
}
