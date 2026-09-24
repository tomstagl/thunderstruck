package com.example.config;

import java.util.HashMap;
import java.util.Map;
import org.springframework.data.redis.cache.RedisCacheConfiguration;

public class CacheConfig {
    private static final ThreadLocal<StringBuilder> bufferCache = ThreadLocal.withInitial(StringBuilder::new);
    private final Map<String, RedisCacheConfiguration> cacheConfigurations = new HashMap<>();

    public RedisCacheConfiguration forName(String name) {
        cacheConfigurations.put("users", RedisCacheConfiguration.defaultCacheConfig());
        return cacheConfigurations.get(name);
    }

    public String render(String value) {
        StringBuilder sb = bufferCache.get();
        sb.setLength(0);
        return sb.append(value).toString();
    }
}
