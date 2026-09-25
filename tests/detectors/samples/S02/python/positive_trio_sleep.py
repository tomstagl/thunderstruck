import trio

async def call():
    for attempt in range(5):
        try:
            return await post()
        except OSError:
            await trio.sleep(2)
