try:
    from resource import struct_rusage
except ImportError:
    pass


def remove_dependents(ids):
    for job_id in ids:
        try:
            Job.fetch(job_id).delete()
        except NoSuchJobError:
            pass


def lookup(table, key):
    value = None
    try:
        value = table[key]
    except (KeyError, IndexError):
        pass
    try:
        value = Device.objects.get(pk=key)
    except Device.DoesNotExist:
        pass
    return value
