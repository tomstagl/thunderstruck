def run(scheduler, log):
    try:
        scheduler.work()
    except:
        log.error("scheduler raised an exception")
        raise
