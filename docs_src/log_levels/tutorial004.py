from logust import logger

logger.set_level("INFO")

level = logger.get_level()
print(f"Current level: {level.name} ({level.value})")

print("DEBUG enabled?", logger.is_level_enabled("DEBUG"))
print("INFO enabled?", logger.is_level_enabled("INFO"))
