package com.example.pool;

import java.sql.Connection;
import java.sql.Statement;
import java.util.concurrent.Executor;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadPoolExecutor;

// The one pool here only services Connection.setNetworkTimeout; the two
// execute(...) calls are JDBC statements, not submissions to it.
public class PoolBase {
    private Executor netTimeoutExecutor;

    void createNetworkTimeoutExecutor() {
        ThreadPoolExecutor executor = (ThreadPoolExecutor) Executors.newCachedThreadPool();
        netTimeoutExecutor = executor;
    }

    void setNetworkTimeout(Connection connection, int timeoutMs) throws Exception {
        connection.setNetworkTimeout(netTimeoutExecutor, timeoutMs);
    }

    void check(Connection connection, String testQuery) throws Exception {
        try (Statement statement = connection.createStatement()) {
            statement.execute(testQuery);
        }
    }

    void init(Connection connection, String sql) throws Exception {
        try (Statement statement = connection.createStatement()) {
            statement.execute(sql);
        }
    }
}
