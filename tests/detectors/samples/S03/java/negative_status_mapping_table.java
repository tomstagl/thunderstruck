package com.example.transport;

import java.net.HttpURLConnection;

// Translates an HTTP status into a transport status code. Nothing here sends
// a request or waits to retry one, so there is no Retry-After to honour.
public final class StatusMapping {

    enum Code { INTERNAL, UNAVAILABLE, UNKNOWN }

    enum FrameError {
        NO_ERROR(0x0), PROTOCOL_ERROR(0x1);

        private final long code;

        FrameError(long code) { this.code = code; }

        long code() { return code; }
    }

    static final class Info {
        private boolean transparentRetry;

        Info setIsTransparentRetry(boolean value) {
            this.transparentRetry = value;
            return this;
        }
    }

    static Code toCode(int httpStatusCode) {
        switch (httpStatusCode) {
            case HttpURLConnection.HTTP_BAD_REQUEST:
                return Code.INTERNAL;
            case 429:
            case HttpURLConnection.HTTP_BAD_GATEWAY:
            case HttpURLConnection.HTTP_UNAVAILABLE:
            case HttpURLConnection.HTTP_GATEWAY_TIMEOUT:
                return Code.UNAVAILABLE;
            default:
                return Code.UNKNOWN;
        }
    }

    static int tableSize(FrameError[] errors) {
        return (int) errors[errors.length - 1].code() + 1;
    }

    static Info describe(boolean transparent) {
        return new Info().setIsTransparentRetry(transparent);
    }
}
