def export_users(session):
    return session.query(User).filter(User.active.is_(True)).all()
