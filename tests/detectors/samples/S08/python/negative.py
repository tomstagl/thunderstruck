import asyncio

async def enrich_all(ids):
    semaphore = asyncio.Semaphore(8)

    async def bounded(i):
        async with semaphore:
            return await enrich(i)

    return await asyncio.gather(*[bounded(i) for i in ids])
