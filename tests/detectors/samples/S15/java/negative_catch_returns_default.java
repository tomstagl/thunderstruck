package com.example.client;
import java.util.Collections;
import java.util.List;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;
public class RecClient {
    private final RestTemplate restTemplate;
    public RecClient(RestTemplate restTemplate) { this.restTemplate = restTemplate; }
    public List<String> get(String id) {
        try {
            return List.of(restTemplate.getForObject("/recs/{id}", String[].class, id));
        } catch (RestClientException e) {
            return Collections.emptyList();
        }
    }
}
