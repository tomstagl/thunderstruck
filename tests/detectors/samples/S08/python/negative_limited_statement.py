from sqlmodel import col, select

from .models import Item


def read_items(session, skip: int = 0, limit: int = 100):
    statement = (
        select(Item).order_by(col(Item.created_at).desc()).offset(skip).limit(limit)
    )
    items = session.exec(statement).all()
    return items
