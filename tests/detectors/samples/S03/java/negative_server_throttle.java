package com.example.web;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LoginController {
    private final Map<String, Integer> failedAttempts = new ConcurrentHashMap<>();

    @PostMapping("/login")
    public ResponseEntity<Void> login(String user) {
        int attempts = failedAttempts.getOrDefault(user, 0);
        if (attempts > 5) {
            return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS).build();
        }
        return ResponseEntity.ok().build();
    }
}
