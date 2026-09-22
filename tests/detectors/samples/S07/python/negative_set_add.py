def unique_ids(items):
    seen = set()
    for item in items:
        seen.add(item["id"])
    ordered = list(seen)
    ordered.insert(0, "header")
    return ordered
