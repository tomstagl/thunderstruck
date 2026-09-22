def sync_all():
    page = load_checkpoint()
    while True:
        body = get_page(page)
        for item in body["items"]:
            db.upsert(item)
        save_checkpoint(page + 1)
        if not body["has_more"]:
            break
        page += 1
