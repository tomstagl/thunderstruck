package com.example.sync;

import java.util.List;

// The position is recorded on a persisted progress entity after every page.
public class CatalogSync {
    private final CatalogApi api;
    private final SyncStateRepository states;

    public CatalogSync(CatalogApi api, SyncStateRepository states) {
        this.api = api;
        this.states = states;
    }

    public void run() {
        SyncState state = states.load("catalog");
        long offset = state.getLastOffset();
        boolean hasMore = true;
        while (hasMore) {
            List<String> items = api.list(offset, 100);
            hasMore = items.size() == 100;
            items.forEach(this::apply);
            offset += items.size();
            state.setLastOffset(offset);
        }
    }

    private void apply(String item) { }
}

interface CatalogApi {
    List<String> list(long offset, int limit);
}

interface SyncStateRepository {
    SyncState load(String name);
}

interface SyncState {
    long getLastOffset();
    void setLastOffset(long offset);
}
