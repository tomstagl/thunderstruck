package com.example.grpc;

import example.OrderServiceGrpc;
import io.grpc.ManagedChannel;

public class OrderClient {
    private final OrderServiceGrpc.OrderServiceBlockingStub stub;

    public OrderClient(ManagedChannel channel) {
        this.stub = OrderServiceGrpc.newBlockingStub(channel);
    }

    public String getOrder(String id) {
        return stub.getOrder(id);
    }
}
