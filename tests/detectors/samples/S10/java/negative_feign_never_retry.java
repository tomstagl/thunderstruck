class Clients {
    PaymentsApi payments() {
        return Feign.builder()
            .retryer(Retryer.NEVER_RETRY)
            .target(PaymentsApi.class, "https://payments");
    }
}
