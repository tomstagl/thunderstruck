package com.example.io;

import java.io.Closeable;
import java.io.IOException;

// A parameter named ignored/expected/unused, or the unnamed `_`, declares the
// swallow deliberate. That is the convention IntelliJ's and Error Prone's
// empty-catch checks honour.
public class Resources {
    public static void closeQuietly(Closeable c) {
        try {
            c.close();
        } catch (IOException ignored) {
        }
    }

    public static Integer parseOrNull(String s) {
        try {
            return Integer.parseInt(s);
        } catch (final NumberFormatException expected) { }
        return null;
    }

    public static Object lookup(Class<?> type) {
        try {
            return type.getMethod("toString");
        }
        catch (NoSuchMethodException | SecurityException ignored) {
        }
        return null;
    }

    public static void sleepBriefly() {
        try {
            Thread.sleep(10);
        } catch (Throwable ignored0) {
        }
    }

    public static void stop(Runnable r) {
        try {
            r.run();
        } catch (RuntimeException _) {
        }
    }
}
