import org.springframework.jdbc.core.JdbcTemplate;

class Repo {
    private final JdbcTemplate jdbc;

    int count() {
        return jdbc.queryForObject("SELECT count(*) FROM orders", Integer.class);  // boundary: database
    }
}
