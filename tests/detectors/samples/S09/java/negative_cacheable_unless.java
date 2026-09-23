package com.example.users;

import java.util.Optional;
import org.springframework.cache.annotation.Cacheable;

public interface UserRepository {
    String USERS_BY_LOGIN_CACHE = "usersByLogin";

    @Cacheable(cacheNames = USERS_BY_LOGIN_CACHE, unless = "#result == null")
    Optional<String> findOneByLogin(String login);

    @Cacheable(
            cacheNames = "usersByEmail",
            key = "#email",
            unless = "#result == null")
    Optional<String> findOneByEmail(String email);
}
