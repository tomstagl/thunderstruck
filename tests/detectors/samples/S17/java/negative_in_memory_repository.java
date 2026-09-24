package com.example.users;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class InMemoryUserRepository {
    private final Map<Long, String> inMemoryUsers = new ConcurrentHashMap<>();

    public void save(long id, String name) {
        inMemoryUsers.put(id, name);
    }
}
