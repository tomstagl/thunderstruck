package com.example.workers;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

// The pool runs loaders the class builds itself, one per shard, from a local
// variable. No caller hands it work to prioritise.
class Loader {
    private final ExecutorService workers = Executors.newFixedThreadPool(4);

    public void start(List<String> shards) {
        for (String s : shards) {
            ShardLoader loader = new ShardLoader(s);
            workers.submit(loader);
        }
    }
}

class ShardLoader implements Runnable {
    ShardLoader(String shard) { }

    public void run() { }
}
