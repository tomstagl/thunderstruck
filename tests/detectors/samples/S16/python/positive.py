from celery.schedules import crontab

beat_schedule = {
    "nightly-report": {"task": "reports.nightly", "schedule": crontab(minute=0, hour=3)},
}
