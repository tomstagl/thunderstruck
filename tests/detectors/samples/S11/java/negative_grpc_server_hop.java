package com.example.grpc;

import example.InventoryGrpc;
import example.OrderReply;
import example.OrderRequest;
import example.OrderServiceGrpc;
import example.StockRequest;
import io.grpc.stub.StreamObserver;

public class OrderService extends OrderServiceGrpc.OrderServiceImplBase {
    private final InventoryGrpc.InventoryBlockingStub inventory;

    public OrderService(InventoryGrpc.InventoryBlockingStub inventory) {
        this.inventory = inventory;
    }

    @Override
    public void placeOrder(OrderRequest request, StreamObserver<OrderReply> responseObserver) {
        inventory.reserve(StockRequest.newBuilder().setSku(request.getSku()).build());
        responseObserver.onNext(OrderReply.newBuilder().setAccepted(true).build());
        responseObserver.onCompleted();
    }
}
