package com.example.client;

import java.util.List;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.web.client.RestTemplate;

public class VisitsClient {
    private final RestTemplate restTemplate;
    private final CircuitBreakerFactory<?, ?> cbFactory;

    public VisitsClient(RestTemplate restTemplate, CircuitBreakerFactory<?, ?> cbFactory) {
        this.restTemplate = restTemplate;
        this.cbFactory = cbFactory;
    }

    public List<?> visitsFor(String petId) {
        return cbFactory.create("visits").run(
                () -> restTemplate.getForObject("http://visits/pets/{id}", List.class, petId),
                t -> List.of());
    }
}
