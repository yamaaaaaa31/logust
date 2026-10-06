import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

from logust import logger
from logust.contrib import TailSampler, add_event_fields
from logust.contrib.starlette import RequestLoggerMiddleware

logger.remove()
logger.add(sys.stdout, format="{level:<7} | {extra[path]} tenant={extra[tenant]}")

app = FastAPI()
app.add_middleware(
    RequestLoggerMiddleware,
    canonical=True,
    sampler=TailSampler(
        rate=0.0,
        slow_ms=1000,
        keep_if=lambda event: event.get("tenant") == "enterprise",
    ),
)


@app.get("/reports")
async def reports(tenant: str):
    add_event_fields(tenant=tenant)
    return {"ok": True}


client = TestClient(app)
for tenant in ["free", "enterprise", "free"]:
    client.get("/reports", params={"tenant": tenant})
