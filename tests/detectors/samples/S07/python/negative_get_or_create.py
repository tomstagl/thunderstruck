def store_result(session, task_cls, task_id, result):
    task = session.query(task_cls).filter(task_cls.task_id == task_id).first()
    if not task:
        task = task_cls(task_id)
        task.task_id = task_id
        session.add(task)
        session.flush()
    task.result = result
    session.commit()
