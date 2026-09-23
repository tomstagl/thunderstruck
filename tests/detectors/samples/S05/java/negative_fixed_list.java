package com.example.client;
import java.util.List;
import org.springframework.web.client.RestTemplate;
public class HealthPinger {
    private final RestTemplate restTemplate;
    public HealthPinger(RestTemplate restTemplate) { this.restTemplate = restTemplate; }
    public void ping() {
        for (String url : List.of("https://a.example.com/health", "https://b.example.com/health")) {
            restTemplate.getForObject(url, String.class);
        }
    }
}
