import asyncio

async def profile(user_id):
    user, prefs = await asyncio.gather(get_user(user_id), get_prefs(user_id))
    return {"user": user, "prefs": prefs}
