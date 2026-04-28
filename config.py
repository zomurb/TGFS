import os
from dotenv import load_dotenv

load_dotenv()

API_ID = os.getenv("TG_API_ID")
API_HASH = os.getenv("TG_API_HASH")
CHUNK_SIZE = 48 * 1024 * 1024
