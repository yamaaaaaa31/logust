from fastapi import FastAPI

from logust.contrib.starlette import setup_fastapi

app = FastAPI()
setup_fastapi(app, skip_routes=["/health"])


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/items/{item_id}")
async def read_item(item_id: int):
    return {"item_id": item_id}
