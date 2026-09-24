package com.example.catalog;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.cache.annotation.Cacheable;

public class ProductLookup {
    private final Map<String, String> productCache = new ConcurrentHashMap<>();

    public String get(String sku) {
        return productCache.computeIfAbsent(sku, this::fetchFromDb);
    }

    @Cacheable(value = "prices", sync = true)
    public String price(String sku) {
        return fetchFromDb(sku);
    }

    private String fetchFromDb(String sku) { return "product-" + sku; }
}
