def summarise(messages):
    created = [m for m in messages if m.created]
    return len(created)
