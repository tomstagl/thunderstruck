def make_plugins(pages):
    plugins = {}
    for page in pages:
        for data in page["data"]:
            plugins[data["slug"]] = Plugin(
                title=data["title"],
                homepage_url=data["homepage_url"],
                access_token=data["token"],
            )
    return plugins
