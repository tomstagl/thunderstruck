def sync_all():
    page = 1
    while True:
        body = get_page(page)
        for item in body["items"]:
            db.insert(item)
        if not body["has_more"]:
            break
        page += 1
