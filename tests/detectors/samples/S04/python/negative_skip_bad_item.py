import logging
log = logging.getLogger(__name__)

def parse_all(lines):
    out = []
    for line in lines:
        try:
            out.append(int(line))
        except Exception:
            log.warning("skipping malformed line %r", line)
            continue
    return out
