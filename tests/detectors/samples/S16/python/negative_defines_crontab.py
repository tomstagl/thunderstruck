class crontab(BaseSchedule):
    def __init__(self, minute="*", hour="*"):
        self.minute = minute
        self.hour = hour


def cron_schedule(spec):
    return spec
