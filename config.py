import os
from dotenv import load_dotenv

load_dotenv()

TG_API_ID = int(os.getenv("TG_API_ID", "0"))
TG_API_HASH = os.getenv("TG_API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

CHUNK_SIZE = 48 * 1024 * 1024  # 48 MB
DB_PATH = "tgfs.db"
