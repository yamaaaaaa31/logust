from logust import logger
from logust.contrib import debug_fn, log_fn


@debug_fn
def parse_row(row):
    return row.split(",")


@log_fn
def import_file(rows):
    return [parse_row(row) for row in rows]


logger.set_level("INFO")
import_file(["a,b", "c,d"])
