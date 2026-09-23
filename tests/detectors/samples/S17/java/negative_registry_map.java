package com.example.registry;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class HandlerRegistry {
    private final Map<String, Runnable> handlers = new ConcurrentHashMap<>();

    public void register(String name, Runnable handler) {
        handlers.put(name, handler);
    }
}
