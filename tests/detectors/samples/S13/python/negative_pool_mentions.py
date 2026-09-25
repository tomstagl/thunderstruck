from sqlalchemy import engine_from_config, pool

POOL_CHOICES = [("prefork", "Prefork pool"), ("solo", "Solo pool")]


def run_migrations(config):
    engine = engine_from_config(config, poolclass=pool.NullPool)
    with engine.connect() as connection:
        connection.execute("SELECT 1")
