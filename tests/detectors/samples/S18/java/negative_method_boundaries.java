package com.example.orders;

import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.function.Consumer;
import org.springframework.web.bind.annotation.RequestParam;

// Each method validates its own input first. The call and the validation
// below are in different methods, which the brief's header regex did not
// separate: a multi-line parameter list, a package-private method, a
// parameter annotation with its own parentheses, a lambda field, and a
// brace on its own line.
public class OrderService {
    private final HttpClient client = HttpClient.newHttpClient();

    public String load(HttpRequest req) throws Exception {
        return client.send(req, HttpResponse.BodyHandlers.ofString()).body();
    }

    public void create(
            String name,
            String email) {
        if (name == null) {
            throw new IllegalArgumentException("name");
        }
    }

    String reload(HttpRequest req) throws Exception {
        return client.send(req, HttpResponse.BodyHandlers.ofString()).body();
    }

    void rename(String name) {
        if (name == null) {
            throw new IllegalArgumentException("name");
        }
    }

    public String fetchPage(HttpRequest req) throws Exception {
        return client.send(req, HttpResponse.BodyHandlers.ofString()).body();
    }

    public String page(@RequestParam(defaultValue = "1") int page) {
        if (page < 1) {
            throw new IllegalArgumentException("page");
        }
        return "";
    }

    public String refresh(HttpRequest req) throws Exception {
        return client.send(req, HttpResponse.BodyHandlers.ofString()).body();
    }

    private final Consumer<String> check = s -> {
        if (s == null) throw new IllegalArgumentException("s");
    };

    public String again(HttpRequest req) throws Exception
    {
        return client.send(req, HttpResponse.BodyHandlers.ofString()).body();
    }

    private static String[] parse(String value)
    {
        if (value == null) {
            throw new IllegalArgumentException("value");
        }
        return value.split(",");
    }
}
