from sqlalchemy.orm import Session


def load(session: Session, task_id):
    return session.query(Task).filter(Task.task_id == task_id).first()  # boundary: database
