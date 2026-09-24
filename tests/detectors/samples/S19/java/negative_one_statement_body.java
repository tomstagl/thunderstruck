package com.example.io;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;

public class Loader {
    private static final org.slf4j.Logger log = org.slf4j.LoggerFactory.getLogger(Loader.class);

    // One statement on the line after the catch, then the brace.
    public void load(Runnable task) {
        try {
            task.run();
        } catch (RuntimeException e) {
            log.warn("load failed", e);
        }
    }

    // Rethrow on one line, inside a lambda.
    public List<String> readAll(List<Path> paths) {
        return paths.stream().map(p -> {
            try { return Files.readString(p); } catch (IOException e) { throw new UncheckedIOException(e); }
        }).collect(Collectors.toList());
    }

    // try-with-resources with a handled catch.
    public String firstLine(Path path) {
        try (BufferedReader r = Files.newBufferedReader(path)) {
            return r.readLine();
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
