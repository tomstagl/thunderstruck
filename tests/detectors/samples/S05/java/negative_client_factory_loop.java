package com.example.client;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.List;
public class ClientFactory {
    public HttpClient build(List<String> protocols) {
        HttpClient.Builder b = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2));
        for (String p : protocols) {
            System.out.println(p);
        }
        return b.build();
    }
}
