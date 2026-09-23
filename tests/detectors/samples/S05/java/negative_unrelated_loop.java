package com.example.client;
import java.util.Map;
import org.springframework.http.HttpHeaders;
import org.springframework.web.client.RestTemplate;
public class OrderClient {
    private final RestTemplate restTemplate;
    public OrderClient(RestTemplate restTemplate) { this.restTemplate = restTemplate; }
    public String get(String id, Map<String, String> extra) {
        HttpHeaders headers = new HttpHeaders();
        for (Map.Entry<String, String> e : extra.entrySet()) {
            headers.add(e.getKey(), e.getValue());
        }
        return restTemplate.getForObject("/orders/{id}", String.class, id);
    }
}
