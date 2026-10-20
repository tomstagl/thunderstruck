def import_rows(session, rows, dry_run):
    for row in rows:
        event = Event(**row)
        if not dry_run:
            session.add(event)
    session.commit()
