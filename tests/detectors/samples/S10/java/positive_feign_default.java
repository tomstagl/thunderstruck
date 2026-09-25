class Clients {
    PaymentsApi payments() {
        return Feign.builder()
            .encoder(new JacksonEncoder())
            .decoder(new JacksonDecoder())
            .target(PaymentsApi.class, "https://payments");
    }
}
