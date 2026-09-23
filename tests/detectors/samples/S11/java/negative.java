package com.example.grpc;

import example.OrderServiceGrpc;
import io.grpc.ManagedChannel;
import java.util.concurrent.TimeUnit;

public class OrderClient {
    private final OrderServiceGrpc.OrderServiceBlockingStub stub;

    public OrderClient(ManagedChannel channel) {
        this.stub = OrderServiceGrpc.newBlockingStub(channel);
    }

    public String getOrder(String id) {
        return stub.withDeadlineAfter(2, TimeUnit.SECONDS).getOrder(id);
    }
}
