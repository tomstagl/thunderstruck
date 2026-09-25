from concurrent.futures import ThreadPoolExecutor

def render_thumbnails(paths):
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(make_thumb, paths))
