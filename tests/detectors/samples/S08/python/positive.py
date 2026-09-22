import asyncio

async def enrich_all(ids):
    return await asyncio.gather(*[enrich(i) for i in ids])
