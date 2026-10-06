from tqdm import tqdm

from logust import logger

logger.remove()
logger.add(lambda msg: tqdm.write(msg, end=""))

for i in tqdm(range(3), disable=True):
    logger.info("Item {} done", i)
