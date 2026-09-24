package com.example.config;

import io.github.resilience4j.retry.Retry;
import java.util.function.Supplier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.support.RetryTemplate;

@Configuration
public class WarmupConfig {
    @Bean
    public Supplier<String> warmup(RetryTemplate retryTemplate, Retry retry) {
        return Retry.decorateSupplier(retry, () -> retryTemplate.execute(ctx -> "warm"));
    }
}
