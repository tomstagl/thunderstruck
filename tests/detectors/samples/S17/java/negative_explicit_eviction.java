package com.example.auth;

import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.scheduling.annotation.Scheduled;

public class TokenStore {
    private static final int MAX_ENTRIES = 1000;
    private final Map<String, Instant> tokenCache = new ConcurrentHashMap<>();
    private final Map<String, String> nameCache = new ConcurrentHashMap<>();

    public void put(String token, Instant validUntil) {
        tokenCache.put(token, validUntil);
    }

    public void putName(String key, String name) {
        if (nameCache.size() >= MAX_ENTRIES) {
            nameCache.keySet().iterator().next();
        }
        nameCache.put(key, name);
    }

    @Scheduled(fixedDelay = 60000)
    void purge() {
        Instant now = Instant.now();
        tokenCache.values().removeIf(validUntil -> validUntil.isBefore(now));
    }
}
