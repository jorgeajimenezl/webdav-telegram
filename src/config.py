import os

TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
REDIS_HOST = os.getenv("REDIS_HOST")
ACL_USERS = os.getenv("ACL_USERS")
ACL_MODE = os.getenv("ACL_MODE", default="blacklist")
