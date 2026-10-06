from logust import logger

logger.info("Without arguments, {braces} stay as they are: {}")
logger.info("With arguments, double them: {{literal}} and {}", "a value")
