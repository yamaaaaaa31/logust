from contextlib import asynccontextmanager

from fastapi import FastAPI

from logust import logger
from logust.contrib import log_fn
from logust.contrib.starlette import setup_fastapi

logger.add("app.log", rotation="daily", retention="7 days")
logger.add("app.json", serialize=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    logger.complete()


app = FastAPI(lifespan=lifespan)
setup_fastapi(app, skip_routes=["/health"])


@log_fn
async def get_user_from_db(user_id: int):
    return {"id": user_id, "name": "John"}


@app.get("/users/{user_id}")
async def read_user(user_id: int):
    return await get_user_from_db(user_id)


@app.get("/health")
async def health():
    return {"status": "ok"}
