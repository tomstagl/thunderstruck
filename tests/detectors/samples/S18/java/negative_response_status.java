package com.example.web;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ResponseStatusException;

// A ResponseStatusException raised after the call reports what the
// dependency returned (502, 404), not a request that was never valid.
public class PriceController {
    private final RestTemplate rest;
    private final WebClient web;

    public PriceController(RestTemplate rest, WebClient web) {
        this.rest = rest;
        this.web = web;
    }

    public String price(String id) {
        ResponseEntity<String> r = rest.getForEntity("/prices/" + id, String.class);
        if (r.getBody() == null) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY);
        }
        return r.getBody();
    }

    public String name(String id) {
        return web.get().uri("/names/{id}", id).retrieve().bodyToMono(String.class).blockOptional()
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}
