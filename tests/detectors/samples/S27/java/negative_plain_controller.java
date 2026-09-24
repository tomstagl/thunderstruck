package com.example.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {
    @GetMapping("/orders/{id}")
    public String getOrder(String id) throws InterruptedException {
        Thread.sleep(50);
        return jdbcLookup(id);
    }

    private String jdbcLookup(String id) {
        return "order-" + id;
    }
}
