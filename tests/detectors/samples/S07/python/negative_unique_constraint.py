from sqlalchemy.exc import IntegrityError

def signup(session, email):
    user = User(email=email)
    try:
        session.add(user)
        session.commit()
    except IntegrityError:
        session.rollback()
        return None
    return user
