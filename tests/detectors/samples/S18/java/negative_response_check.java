package com.example.pricing;

import java.util.Objects;
import org.springframework.http.ResponseEntity;
import org.springframework.util.Assert;
import org.springframework.web.client.RestTemplate;

// Each check after the call reads what the call returned (the variable it
// assigned, one derived from it, or the response body/status). That is
// response handling, not input validation that came too late.
public class PriceClient {
    private final RestTemplate rest;
    private final javax.validation.Validator validator;

    public PriceClient(RestTemplate rest, javax.validation.Validator validator) {
        this.rest = rest;
        this.validator = validator;
    }

    public Price price(String id) {
        Price p = rest.getForObject("/prices/{id}", Price.class, id);
        Assert.notNull(p, "pricing service returned no body");
        return p;
    }

    public Price price2(String id) {
        ResponseEntity<Price> r = rest.getForEntity("/prices/{id}", Price.class, id);
        return Objects.requireNonNull(r.getBody());
    }

    public Price price3(String id) {
        ResponseEntity<Price> r = rest.getForEntity("/prices/{id}", Price.class, id);
        Price body = r.getBody();
        Objects.requireNonNull(body, "empty body");
        return body;
    }

    public Price price4(String id) {
        Price p = rest.getForObject("/prices/{id}", Price.class, id);
        validator.validate(p);
        return p;
    }

    public String status(java.net.http.HttpClient client, java.net.http.HttpRequest req) throws Exception {
        java.net.http.HttpResponse<String> resp = client.send(req, java.net.http.HttpResponse.BodyHandlers.ofString());
        if (resp.statusCode() >= 400) {
            throw new IllegalArgumentException("bad status " + resp.statusCode());
        }
        return resp.body();
    }

    record Price(long cents) { }
}
