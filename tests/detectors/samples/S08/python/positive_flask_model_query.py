from app.models import User

def export_users():
    return User.query.all()
