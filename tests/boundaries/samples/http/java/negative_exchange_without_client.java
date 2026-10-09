class Market {
    Rate rate(Currency a, Currency b) {
        return ledger.exchange(a, b);
    }
}
