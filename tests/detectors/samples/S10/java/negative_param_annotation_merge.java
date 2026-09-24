package com.example.client;

import org.springframework.retry.annotation.Retryable;
import org.springframework.web.bind.annotation.RequestParam;

public class OrdersController {
    @Retryable(maxAttempts = 3)
    public String refresh() {
        return "ok";
    }

    public String page(@RequestParam(defaultValue = "1") String page) {
        for (int attempt = 0; attempt < 3; attempt++) {
            try {
                return fetch(page);
            } catch (RuntimeException e) {
                if (attempt == 2) {
                    throw e;
                }
            }
        }
        return null;
    }

    private String fetch(String page) {
        return page;
    }
}
