from logust import logger


def build_report() -> dict[str, int]:
    # Imagine this walks a big data structure
    return {"users": 1200, "orders": 3456}


logger.set_level("INFO")

if logger.is_level_enabled("DEBUG"):
    logger.debug("Report: {}", build_report())

logger.info("Done")
