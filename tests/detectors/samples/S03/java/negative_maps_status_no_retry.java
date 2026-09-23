package com.example.client;

import java.net.http.HttpResponse;

public class ErrorMapper {
    public Exception toError(HttpResponse<String> res) {
        if (res.statusCode() == 429) return new RateLimitedException(res.statusCode());
        if (res.statusCode() >= 500) return new UpstreamException(res.statusCode());
        return null;
    }

    static class RateLimitedException extends Exception {
        RateLimitedException(int status) { super("status " + status); }
    }

    static class UpstreamException extends Exception {
        UpstreamException(int status) { super("status " + status); }
    }
}
