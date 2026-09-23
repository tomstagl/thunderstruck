package com.example.config;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ExecutorConfig {
    @Bean
    public ExecutorService taskExecutor() {
        return Executors.newFixedThreadPool(8);
    }
}

class GreeterServer {
    io.grpc.Server start(int port) throws Exception {
        return io.grpc.ServerBuilder.forPort(port)
                .executor(java.util.concurrent.Executors.newFixedThreadPool(2))
                .build()
                .start();
    }
}
