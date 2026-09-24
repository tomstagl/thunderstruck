package com.example.grpc;

import example.GreeterGrpc;
import example.HelloRequest;
import io.grpc.Grpc;
import io.grpc.InsecureChannelCredentials;
import io.grpc.ManagedChannel;
import java.util.concurrent.TimeUnit;

public class HelloClient {
    private final GreeterGrpc.GreeterBlockingStub blockingStub;

    public HelloClient(ManagedChannel channel) {
        blockingStub = GreeterGrpc.newBlockingStub(channel);
    }

    public void greet(String name) {
        System.out.println(blockingStub.sayHello(HelloRequest.newBuilder().setName(name).build()));
    }

    public static void main(String[] args) throws Exception {
        ManagedChannel channel = Grpc.newChannelBuilder("localhost:50051", InsecureChannelCredentials.create())
                .build();
        try {
            new HelloClient(channel).greet(args.length > 0 ? args[0] : "world");
        } finally {
            channel.shutdownNow().awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
