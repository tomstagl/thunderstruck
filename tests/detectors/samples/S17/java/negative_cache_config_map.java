package com.example.config;

import java.util.HashMap;
import java.util.Map;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

public class CacheConfig {
    RedisCacheManager cacheManager(RedisConnectionFactory factory) {
        Map<String, RedisCacheConfiguration> cacheConfigurations = new HashMap<>();
        cacheConfigurations.put("users", RedisCacheConfiguration.defaultCacheConfig());
        return RedisCacheManager.builder(factory)
                .withInitialCacheConfigurations(cacheConfigurations)
                .build();
    }
}
