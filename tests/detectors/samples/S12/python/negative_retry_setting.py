import click


@click.option("--retry-max", help="Maximum amount of retries", default=0, type=int)
def enqueue(retry_max):
    return {"max_retries": retry_max, "retries": 0}
