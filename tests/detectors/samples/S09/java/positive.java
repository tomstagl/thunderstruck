package com.example.catalog;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.cache.annotation.Cacheable;

public class ProductLookup {
    private final Map<String, String> productCache = new ConcurrentHashMap<>();

    public String get(String sku) {
        if (productCache.containsKey(sku)) {
            return productCache.get(sku);
        }
        String value = fetchFromDb(sku);
        productCache.put(sku, value);
        return value;
    }

    @Cacheable("prices")
    public String price(String sku) {
        return fetchFromDb(sku);
    }

    private String fetchFromDb(String sku) { return "product-" + sku; }
}
