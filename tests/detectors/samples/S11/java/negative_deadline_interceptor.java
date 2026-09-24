package com.example.grpc;
import example.OrderServiceGrpc;
import io.grpc.ClientInterceptors;
import io.grpc.ManagedChannel;
public class OrderClient {
    private final OrderServiceGrpc.OrderServiceBlockingStub stub;
    public OrderClient(ManagedChannel channel) {
        this.stub = OrderServiceGrpc.newBlockingStub(ClientInterceptors.intercept(channel, new DeadlineInterceptor(2000)));
    }
    public String getOrder(String id) { return stub.getOrder(id); }
}
