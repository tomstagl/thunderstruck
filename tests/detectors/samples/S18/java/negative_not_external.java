package com.example.runner;

import java.lang.reflect.Method;
import java.util.concurrent.Executor;

// Handing a task to an executor, invoking a method reflectively and building
// a Spring Data Query are not calls to another system; nor is "got" in a
// string.
public class Runner {
    private final Executor executor;
    private final Executor workerPool;

    public Runner(Executor executor, Executor workerPool) {
        this.executor = executor;
        this.workerPool = workerPool;
    }

    public void run(Runnable r, Method m, Object target, String arg) throws Exception {
        executor.execute(r);
        workerPool.execute(r);
        m.invoke(target);
        if (arg == null) {
            throw new IllegalArgumentException("arg");
        }
    }

    public int fetchSize(String table) {
        int size = fetchCount(table);
        if (size < 0) {
            throw new IllegalArgumentException("size");
        }
        return size;
    }

    private int fetchCount(String table) {
        return 0;
    }

    public void check(String[] destinations, Object template, Object process) {
        if (destinations.length > 1) {
            throw new IllegalStateException("one destination must be set (got " + destinations.length + ")");
        }
        Object q = org.springframework.data.mongodb.core.query.Query.query(null);
        java.util.Objects.requireNonNull(process);
    }

    public Object dispatch(Method handler, Object target, Object delegate) throws Exception {
        Object result = handler.invoke(target);
        java.util.Objects.requireNonNull(delegate);
        return result;
    }
}
