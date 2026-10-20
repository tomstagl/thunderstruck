# A guard that skips an empty row is not a lookup of the row: the insert
# that follows it runs on every replay (#58 review).
def import_items(session, items):
    for item in items:
        if not item:
            continue
        session.add(item)
    session.commit()
