package com.example.catalog;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;

public class ImageLookup {
    private final Cache<String, byte[]> imageCache = Caffeine.newBuilder()
            .softValues()
            .build();

    public void put(String key, byte[] image) {
        imageCache.put(key, image);
    }
}
