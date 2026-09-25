def parse_prefix(value):
    prefix = None
    try:
        prefix = int(value)
    except ValueError:
        pass
    try:
        prefix = IPNetwork(value)
    except (AddrFormatError, ValueError):
        pass
    return prefix
