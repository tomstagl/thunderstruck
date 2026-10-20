# celery/backends/database/__init__.py at 508c112 (#58): a stored value that
# fails to decode is dropped without a trace, and the result is returned
# without it.
def meta_from_row(self, data):
    raw_stamps = data.pop("stamps", None)
    if raw_stamps is not None:
        try:
            stamps_info = self.decode(raw_stamps)
            if isinstance(stamps_info, dict):
                if "stamped_headers" in stamps_info:
                    data["stamped_headers"] = stamps_info["stamped_headers"]
        except Exception:
            pass
    return self.meta_from_decoded(data)
