import time

from tqdm import tqdm

from logust import logger

logger.remove()
logger.add(lambda msg: tqdm.write(msg), colorize=True)

for i in tqdm(range(100)):
    time.sleep(0.01)
    if i % 25 == 0:
        logger.info(f"Checkpoint <green>{i}</green> reached")
