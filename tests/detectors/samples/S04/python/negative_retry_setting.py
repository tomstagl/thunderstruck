import sqlalchemy as sa

from .options import Option

defaults = {
    "max_retries": Option(type="int"),
    "result_backend_max_retries": 20,
}


class TaskMeta:
    retries = sa.Column(sa.Integer, nullable=True)


def build_client(factory, conf):
    return factory(max_retries=conf.get("max_retries", 3))
