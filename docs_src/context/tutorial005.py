import sys
import uuid
from dataclasses import dataclass

from logust import logger

logger.remove()
logger.add(sys.stderr, serialize=True)


@dataclass
class Request:
    method: str
    path: str


def handle_request(request):
    req_logger = logger.bind(
        request_id=uuid.uuid4().hex[:8],
        method=request.method,
        path=request.path,
    )
    req_logger.info("Request started")
    # ... process the request ...
    req_logger.info("Request completed")


handle_request(Request("GET", "/orders"))
