package com.example.config;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.support.RetryTemplate;
@Configuration
public class RetryBeans {
    @Bean
    public RetryTemplate retryTemplate() {
        return RetryTemplate.builder().maxAttempts(3).build();
    }
}
