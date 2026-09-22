def save(payload):
    for _ in range(3):
        try:
            return post("/save", payload)
        except Exception:
            continue
    raise RuntimeError("failed")
