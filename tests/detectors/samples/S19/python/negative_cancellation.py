import asyncio


def clear(queue):
    while queue:
        try:
            queue.pop().cancel()
        except (KeyError, GreenletExit):
            pass


async def stop(task):
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def consume(stream):
    try:
        for message in stream:
            handle(message)
    except StopFiltering:
        pass
