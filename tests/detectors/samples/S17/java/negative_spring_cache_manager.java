package com.example.users;

import java.util.HashMap;
import java.util.Map;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;

public class UserWarmer {
    private final CacheManager cacheManager;

    public UserWarmer(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    public Map<String, String> warm(String login, String user) {
        Map<String, String> params = new HashMap<>();
        params.put("login", login);
        Cache cache = cacheManager.getCache("usersByLogin");
        cache.put(login, user);
        return params;
    }
}
