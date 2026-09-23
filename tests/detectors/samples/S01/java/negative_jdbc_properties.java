package com.example.client;

import java.sql.Connection;
import java.sql.DriverManager;
import java.util.Properties;

public class Db {
    public Connection open(String url) throws Exception {
        Properties props = new Properties();
        props.setProperty("connectTimeout", "5");
        return DriverManager.getConnection(url, props);
    }
}
