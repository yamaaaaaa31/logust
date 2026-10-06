import logging

from logust.contrib import InterceptHandler

logging.basicConfig(handlers=[InterceptHandler()], level=logging.INFO, force=True)

logging.getLogger("myapp").info("Routed by a handler you installed yourself")
logging.getLogger("myapp").debug("Below INFO, so the stdlib drops it")
