package com.example.client;

import org.springframework.context.annotation.Bean;
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

public class RestConfig {
    @Bean
    RestTemplate restTemplate() {
        RestTemplate rest = new RestTemplate();
        rest.setRequestFactory(requestFactory());
        return rest;
    }

    @Bean
    RestTemplate otherTemplate() {
        return new RestTemplate(requestFactory());
    }

    private ClientHttpRequestFactory requestFactory() {
        HttpComponentsClientHttpRequestFactory factory = new HttpComponentsClientHttpRequestFactory();
        factory.setConnectionRequestTimeout(2000);
        factory.setConnectTimeout(2000);
        return factory;
    }
}
