import sys
from dataclasses import dataclass

from logust import logger

logger.remove()
logger.add(sys.stderr, format="{level} | {message} | user={extra[user_id]} action={extra[action]}")


@dataclass
class User:
    id: int


def save_settings():
    logger.info("Settings saved")


def process_user_action(user, action):
    with logger.contextualize(user_id=user.id, action=action):
        logger.info("Processing action")
        save_settings()


process_user_action(User(id=42), "update-settings")
