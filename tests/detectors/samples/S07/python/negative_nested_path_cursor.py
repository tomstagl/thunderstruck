def build(root, paths):
    cursor = root
    for path, next_path in zip(paths, paths[1:]):
        cursor = cursor.setdefault(path, make(next_path))
    return root
