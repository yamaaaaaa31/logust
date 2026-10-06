import sys

from logust import logger

logger.remove()
logger.add(sys.stdout, format="{message}")

user_input = "<b>hello</b>"

logger.info("Comment posted: " + user_input)
logger.opt(colors=False).info("Comment posted: " + user_input)
