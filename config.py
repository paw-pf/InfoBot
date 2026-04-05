"""Application configuration and environment setup."""

import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USERS = os.getenv("ALLOWED_USERS", "")
REPORT_CHAT_ID = os.getenv("REPORT_CHAT_ID", "")

# Google Sheets
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

# Shift configuration
NIGHT_SHIFT_START_HOUR = int(os.getenv("NIGHT_SHIFT_START_HOUR", "20"))
DAY_SHIFT_START_HOUR = int(os.getenv("DAY_SHIFT_START_HOUR", "6"))

# Parse allowed users
if ALLOWED_USERS:
    ALLOWED_USERS_SET = set(int(uid.strip()) for uid in ALLOWED_USERS.split(","))
else:
    ALLOWED_USERS_SET = None

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
