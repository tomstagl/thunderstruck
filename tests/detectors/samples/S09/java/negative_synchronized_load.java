package com.example.catalog;

import java.util.HashMap;
import java.util.Map;

public class ProductLookup {
    private final Map<String, String> productCache = new HashMap<>();

    public synchronized String get(String sku) {
        String value = productCache.get(sku);
        if (value == null) {
            value = fetchFromDb(sku);
            productCache.put(sku, value);
        }
        return value;
    }

    private String fetchFromDb(String sku) { return "product-" + sku; }
}
