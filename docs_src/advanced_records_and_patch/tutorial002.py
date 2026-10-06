import time

from logust import logger

logger.remove()

records = []
logger.add_callback(records.append)

logger.info("Starting")
time.sleep(0.25)
logger.warning("Disk usage is at {}%", 91)

record = records[-1]
level = record["level"]
print(f"level:   {level} (no={level.no}, icon={level.icon})")
print(f"is warn: {level == 'WARNING'}")
print(f"file:    {record['file'].name}")
print(f"thread:  {record['thread'].name}")
print(f"process: {record['process'].name}")
print(f"time:    {record['time'].isoformat()}")
print(f"hour:    {record['time'].hour}")
print(f"elapsed: {record['elapsed']}")
