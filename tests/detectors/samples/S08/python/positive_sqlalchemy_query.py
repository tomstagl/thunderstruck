from app.db import session
from app.models import User

def export_users():
    return session.query(User).all()
