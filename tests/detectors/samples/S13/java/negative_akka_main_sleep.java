package com.example.app;

import akka.actor.typed.ActorSystem;
import akka.actor.typed.javadsl.Behaviors;

// The sleep is on the launcher's main thread, not inside an actor.
public class Main {
    public static void main(String[] args) throws Exception {
        ActorSystem<String> system = ActorSystem.create(Behaviors.setup(ctx -> Behaviors.empty()), "app");
        Thread.sleep(5000);
        system.terminate();
    }
}
