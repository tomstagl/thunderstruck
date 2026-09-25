_template_cache = {}


def get_template(name):
    if name not in _template_cache:
        _template_cache[name] = load_template(name)
    return _template_cache[name]


def on_templates_changed():
    _template_cache.clear()
