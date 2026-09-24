package com.example.catalog;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class ProductLookup {
    private final Map<String, String> cache = new ConcurrentHashMap<>();

    public void put(String sku, String value) {
        cache.put(sku, value);
    }
}
