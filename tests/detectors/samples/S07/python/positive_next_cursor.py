def sync_all(client, db):
    cursor = None
    while True:
        resp = client.list_events(cursor=cursor)
        for item in resp["items"]:
            db.insert(item)
        cursor = resp["next_cursor"]
        if not cursor:
            break
