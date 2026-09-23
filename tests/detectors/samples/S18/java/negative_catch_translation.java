package com.example.http;

import java.net.URISyntaxException;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

// The URL is checked by toURI() before the send; the catch below only
// translates that failure. A throw inside a catch is not late validation.
public class Executor {
    private final HttpClient client = HttpClient.newHttpClient();

    public String execute(String url) throws Exception {
        try {
            HttpRequest req = HttpRequest.newBuilder(new java.net.URL(url).toURI()).build();
            return client.send(req, HttpResponse.BodyHandlers.ofString()).body();
        } catch (URISyntaxException e) {
            throw new IllegalArgumentException("Malformed URL: " + url, e);
        }
    }

    public String executeAllman(String url) throws Exception {
        try {
            HttpRequest req = HttpRequest.newBuilder(new java.net.URL(url).toURI()).build();
            return client.send(req, HttpResponse.BodyHandlers.ofString()).body();
        }
        catch (URISyntaxException e)
        {
            throw new IllegalArgumentException("Malformed URL: " + url, e);
        }
    }
}
