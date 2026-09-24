package com.example.status;

import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

// A switch's default branch that throws is an exhaustiveness check on the
// response, not input validation that came too late.
public class StatusClient {
    private final HttpClient client = HttpClient.newHttpClient();

    public Status status(HttpRequest req) throws Exception {
        String body = client.send(req, HttpResponse.BodyHandlers.ofString()).body();
        switch (body) {
            case "UP": return Status.UP;
            default: throw new IllegalArgumentException("unknown status " + body);
        }
    }

    public Status parse(HttpRequest req) throws Exception {
        String body = client.send(req, HttpResponse.BodyHandlers.ofString()).body();
        return switch (body) {
            case "UP" -> Status.UP;
            default -> throw new IllegalArgumentException("unknown status " + body);
        };
    }

    enum Status { UP }
}
