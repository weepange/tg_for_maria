import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set. Please check your .env file.")

# Run mode: "polling" or "webhook"
RUN_MODE = os.getenv("RUN_MODE", "polling").lower()

# Webhook configurations
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")

# Construct the full webhook URL
WEBHOOK_URL = f"{WEBHOOK_HOST.rstrip('/')}{WEBHOOK_PATH}" if WEBHOOK_HOST else None

# Webserver settings
PORT = int(os.getenv("PORT", 8080))
HOST = os.getenv("HOST", "0.0.0.0")

# Timezone settings
import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

env_tz = os.getenv("TIMEZONE")
if env_tz:
    try:
        BOT_TZ = ZoneInfo(env_tz)
    except ZoneInfoNotFoundError:
        BOT_TZ = datetime.datetime.now().astimezone().tzinfo
else:
    BOT_TZ = datetime.datetime.now().astimezone().tzinfo
