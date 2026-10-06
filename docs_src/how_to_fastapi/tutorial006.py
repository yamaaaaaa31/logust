from fastapi import FastAPI

from logust import logger
from logust.contrib import add_event_fields
from logust.contrib.starlette import setup_fastapi

logger.add("app.json", serialize=True)

app = FastAPI()
setup_fastapi(
    app,
    canonical=True,
    sample_rate=0.02,
    slow_ms=1000,
    skip_routes=["/health"],
)


@app.post("/checkout")
async def checkout(user_id: str):
    add_event_fields(
        {"user.id": user_id},
        feature_checkout_v2=True,
        payment_provider="stripe",
    )
    return {"ok": True}
