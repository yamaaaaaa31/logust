import asyncio

from logust.contrib import debug_fn


@debug_fn
async def fetch_user(user_id):
    await asyncio.sleep(0.05)
    return {"id": user_id, "name": "Alice"}


async def main():
    user = await fetch_user(123)
    print(user)


asyncio.run(main())
