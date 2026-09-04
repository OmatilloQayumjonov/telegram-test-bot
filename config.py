import os
from pathlib import Path
from dotenv import load_dotenv

# .env faylini yuklash
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "8970837149:AAGb7EhM3tkWz1SRP2PjNV8Hwc0rNHQAJ8M").strip()
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "1184083915").strip()

# Adminlar ID ro'yxati (int formatda)
ADMIN_IDS = [1184083915]
if ADMIN_IDS_RAW:
    for item in ADMIN_IDS_RAW.split(","):
        item = item.strip()
        if item.isdigit() and int(item) not in ADMIN_IDS:
            ADMIN_IDS.append(int(item))

DATABASE_PATH = os.getenv("DATABASE_PATH", "data/bot.db").strip()
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_FULL_PATH = BASE_DIR / DATABASE_PATH
DB_FULL_PATH.parent.mkdir(parents=True, exist_ok=True)
