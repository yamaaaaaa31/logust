from fastapi import FastAPI

from logust.contrib import RequestLoggerMiddleware

app = FastAPI()
app.add_middleware(RequestLoggerMiddleware)


@app.get("/users/{user_id}")
async def read_user(user_id: int):
    return {"user_id": user_id}
