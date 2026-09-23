package com.example.reflect;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class MetadataResolver {
    private final Map<Class<?>, String> metadataCache = new ConcurrentHashMap<>();

    public String of(Class<?> type) {
        String meta = metadataCache.get(type);
        if (meta == null) {
            meta = type.getName();
            metadataCache.put(type, meta);
        }
        return meta;
    }
}
