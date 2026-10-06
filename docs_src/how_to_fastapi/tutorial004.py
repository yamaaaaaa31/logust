import sys

from fastapi import FastAPI

from logust import logger
from logust.contrib.starlette import get_request_id, setup_fastapi

logger.remove()
logger.add(
    sys.stderr,
    format="{time} | {level:<8} | {extra[request_id]} | {message}",
)

app = FastAPI()
setup_fastapi(app)


@app.get("/users/{user_id}")
async def read_user(user_id: int):
    logger.info("Loading user {}", user_id)
    return {"user_id": user_id, "request_id": get_request_id()}
