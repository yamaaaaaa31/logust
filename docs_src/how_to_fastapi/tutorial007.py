from fastapi import FastAPI

from logust.contrib import TailSampler
from logust.contrib.starlette import setup_fastapi

app = FastAPI()
setup_fastapi(
    app,
    canonical=True,
    sampler=TailSampler(
        rate=0.01,
        slow_ms=750,
        keep_if=lambda event: event.get("tenant") == "enterprise",
    ),
)
