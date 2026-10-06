from fastapi import FastAPI

from logust.contrib import RequestLoggerMiddleware

app = FastAPI()
app.add_middleware(
    RequestLoggerMiddleware,
    skip_routes=["/health", "/metrics"],
    skip_regexes=[r"^/docs", r"^/openapi\.json$"],
    include_request_body=True,
    max_body_size=1000,
    mask_sensitive_data=True,
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/login")
async def login(credentials: dict):
    return {"ok": True}
