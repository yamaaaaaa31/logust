import sys
import time

from logust import logger
from logust.contrib import add_event_fields, canonical_event

logger.remove()
logger.add(sys.stdout, serialize=True)


def send_invoices(customer_ids):
    # ... send one invoice per customer ...
    add_event_fields(invoices_sent=len(customer_ids))


def run_job():
    start = time.perf_counter()
    with canonical_event({"event": "job.invoices"}) as event:
        add_event_fields(batch="2026-10")
        send_invoices(["c_1", "c_2", "c_3"])
        event["duration_ms"] = round((time.perf_counter() - start) * 1000, 3)
        logger.info("job.invoices", **event)


run_job()
print("Outside an event:", add_event_fields(outside=True))
