import asyncio
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

from logust import logger
from logust.contrib.starlette import RequestLoggerMiddleware

logger.remove()
logger.add(
    sys.stdout,
    format="{level:<7} | {extra[path]} {extra[status_code]} {extra[outcome]} "
    "{extra[duration_ms]}ms",
)

app = FastAPI()
app.add_middleware(
    RequestLoggerMiddleware,
    canonical=True,
    sample_rate=0.0,
    slow_ms=50,
    always_keep_errors=True,
)


@app.get("/fast")
async def fast():
    return {"ok": True}


@app.get("/slow")
async def slow():
    await asyncio.sleep(0.06)
    return {"ok": True}


@app.get("/broken")
async def broken():
    raise RuntimeError("database is down")


client = TestClient(app, raise_server_exceptions=False)
for path in ["/fast", "/fast", "/slow", "/broken"]:
    client.get(path)
