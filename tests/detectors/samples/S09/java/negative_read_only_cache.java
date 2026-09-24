package com.example.catalog;

import java.util.Map;

public class CountryNames {
    private final Map<String, String> nameCache;

    public CountryNames(Map<String, String> preloaded) {
        this.nameCache = Map.copyOf(preloaded);
    }

    public String name(String code) {
        return nameCache.get(code);
    }
}
