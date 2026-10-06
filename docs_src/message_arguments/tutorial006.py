from logust import logger


class Report:
    def __format__(self, format_spec: str) -> str:
        print("  ...formatting the report...")
        return "REPORT"


logger.set_level("INFO")

logger.debug(f"f-string: {Report()}")
logger.debug("arguments: {}", Report())
logger.info("arguments: {}", Report())
