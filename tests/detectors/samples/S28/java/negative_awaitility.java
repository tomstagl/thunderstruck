package com.example.inventory;

import static org.awaitility.Awaitility.await;

import java.time.Duration;

public class StockEventually {
    public void waitForStock(StockLedger ledger) {
        await().atMost(Duration.ofSeconds(5)).until(ledger::hasStock);
    }
}
