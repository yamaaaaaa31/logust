import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

from logust import logger
from logust.contrib.starlette import RequestLoggerMiddleware, get_request_id

logger.remove()
logger.add(sys.stdout, format="{level:<7} | {extra[request_id]} | {message}")

app = FastAPI()
app.add_middleware(RequestLoggerMiddleware, canonical=True)


@app.get("/me")
async def me():
    logger.info("Loading the profile")
    return {"request_id": get_request_id()}


client = TestClient(app)
print(client.get("/me", headers={"x-request-id": "req-abc-123"}).json())
print(client.get("/me").json())
