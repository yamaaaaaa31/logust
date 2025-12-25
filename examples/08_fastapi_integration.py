#!/usr/bin/env python3
"""FastAPI integration example - Using Logust with FastAPI applications.

This example demonstrates how to integrate Logust with FastAPI for
request logging, error handling, and structured logging in web applications.

Requirements:
    pip install fastapi uvicorn

Run this example:
    python 08_fastapi_integration.py

Then visit:
    http://localhost:8000/
    http://localhost:8000/users/123
    http://localhost:8000/error
"""

import sys
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from logust import logger

# Check if FastAPI is installed
try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import JSONResponse
except ImportError:
    print("FastAPI is not installed. Install it with:")
    print("  pip install fastapi uvicorn")
    sys.exit(1)


# Configure Logust for production-like setup
def setup_logging() -> None:
    """Configure logging for the FastAPI application."""
    # JSON logs for production (comment out for development)
    # logger.add("logs/app.json", serialize=True, rotation="100 MB", retention="30 days")

    # Error-only file
    # logger.add("logs/errors.log", level="ERROR", rotation="50 MB")

    # Set appropriate level
    logger.set_level("DEBUG")

    logger.info("Logging configured for FastAPI application")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    setup_logging()
    logger.info("FastAPI application starting up")
    yield
    logger.info("FastAPI application shutting down")
    logger.complete()  # Flush all pending logs


app = FastAPI(
    title="Logust FastAPI Example",
    lifespan=lifespan,
)


# Middleware for request logging
@app.middleware("http")
async def log_requests(request: Request, call_next: Any) -> Any:
    """Middleware to log all HTTP requests."""
    # Generate unique request ID
    request_id = str(uuid.uuid4())[:8]

    # Create request-specific logger
    request_logger = logger.bind(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        client_ip=request.client.host if request.client else "unknown",
    )

    request_logger.info("Request started")

    try:
        response = await call_next(request)
        request_logger.bind(status_code=response.status_code).info("Request completed")
        return response
    except Exception as e:
        request_logger.opt(exception=True).error(f"Request failed: {e}")
        raise


# Exception handler for unhandled exceptions
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all unhandled exceptions."""
    logger.opt(exception=True).error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Routes
@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    logger.debug("Root endpoint accessed")
    return {"message": "Welcome to Logust + FastAPI!"}


@app.get("/users/{user_id}")
async def get_user(user_id: int) -> dict[str, Any]:
    """Get user by ID with context logging."""
    user_logger = logger.bind(user_id=user_id)

    user_logger.debug("Fetching user from database")

    # Simulate user lookup
    if user_id == 0:
        user_logger.warning("Invalid user ID requested")
        raise HTTPException(status_code=400, detail="Invalid user ID")

    if user_id > 1000:
        user_logger.info("User not found")
        raise HTTPException(status_code=404, detail="User not found")

    user_logger.success("User retrieved successfully")
    return {"user_id": user_id, "name": f"User {user_id}", "email": f"user{user_id}@example.com"}


@app.post("/orders")
async def create_order(request: Request) -> dict[str, Any]:
    """Create an order with detailed logging."""
    order_id = str(uuid.uuid4())[:8]

    with logger.contextualize(order_id=order_id):
        logger.info("Order creation started")
        logger.debug("Validating order data")
        logger.debug("Checking inventory")
        logger.info("Order created successfully")

    return {"order_id": order_id, "status": "created"}


@app.get("/error")
async def trigger_error() -> None:
    """Endpoint that triggers an error for testing."""
    logger.warning("About to trigger an intentional error")
    raise ValueError("This is an intentional error for testing")


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    logger.trace("Health check called")
    return {"status": "healthy"}


if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        print("uvicorn is not installed. Install it with:")
        print("  pip install uvicorn")
        sys.exit(1)

    print("\nStarting FastAPI server with Logust logging...")
    print("Visit http://localhost:8000 in your browser")
    print("Try these endpoints:")
    print("  GET  /           - Root endpoint")
    print("  GET  /users/123  - Get user")
    print("  POST /orders     - Create order")
    print("  GET  /error      - Trigger error")
    print("  GET  /health     - Health check")
    print("\nPress Ctrl+C to stop\n")

    uvicorn.run(app, host="0.0.0.0", port=8000)
