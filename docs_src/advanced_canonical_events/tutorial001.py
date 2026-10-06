import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

from logust import logger
from logust.contrib import add_event_fields
from logust.contrib.starlette import RequestLoggerMiddleware

logger.remove()
logger.add(sys.stdout, serialize=True)

app = FastAPI()
app.add_middleware(RequestLoggerMiddleware, canonical=True)


@app.post("/checkout")
async def checkout(user_id: str):
    add_event_fields({"user.id": user_id}, payment_provider="stripe", items=3)
    return {"ok": True}


client = TestClient(app)
client.post("/checkout", params={"user_id": "u_123"})
