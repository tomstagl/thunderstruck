class UserService {
    Mono<User> find(long id) {
        return Mono.fromCallable(() -> jdbcTemplate.queryForObject(SQL, MAPPER, id))
            .map(this::enrich)
            .map(this::audit)
            .filter(Objects::nonNull)
            .map(this::a)
            .map(this::b)
            .map(this::c)
            .map(this::d)
            .map(this::e)
            .map(this::f)
            .map(this::g)
            .map(this::h)
            .subscribeOn(Schedulers.boundedElastic());
    }
}
