package com.example.client;

import org.springframework.web.client.RestTemplate;

public class StatusPoller {
    private final RestTemplate restTemplate;
    private volatile boolean running = true;

    public StatusPoller(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public void poll() throws InterruptedException {
        while (running) {
            restTemplate.getForObject("https://api.example.com/status", String.class);
            Thread.sleep(5000);
        }
    }
}
