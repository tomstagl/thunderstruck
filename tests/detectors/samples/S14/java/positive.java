package com.example.workers;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class UnboundedPool {
    private final ThreadPoolExecutor executor = new ThreadPoolExecutor(
            4, 4, 60, TimeUnit.SECONDS, new LinkedBlockingQueue<>());
    private final ExecutorService fixed = Executors.newFixedThreadPool(4);
    private final java.util.Deque<String> pending = new java.util.concurrent.LinkedBlockingDeque<String>();
}

class RabbitIntake {
    void start(com.rabbitmq.client.Channel channel, com.rabbitmq.client.Consumer consumer) throws Exception {
        channel.basicConsume("intake", false, consumer);
    }
}
