def call():
    attempts = 0
    while attempts < 5:
        try:
            return post()
        except Exception:
            attempts += 1
