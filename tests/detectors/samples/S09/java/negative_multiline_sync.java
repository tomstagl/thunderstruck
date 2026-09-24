package com.example.catalog;

import org.springframework.cache.annotation.Cacheable;

public class PriceService {
    @Cacheable(
            cacheNames = "prices",
            key = "#sku",
            unless = "#result == null",
            condition = "#sku != null",
            sync = true)
    public String price(String sku) {
        return load(sku);
    }

    private String load(String sku) { return "price-" + sku; }
}
