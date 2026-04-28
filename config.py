import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")

load_dotenv(dotenv_path=ENV_PATH)

def _get_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


API_ID = int(_get_env("API_ID", "TG_API_ID", default="0"))
API_HASH = _get_env("API_HASH", "TG_API_HASH", default="")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

CHUNK_SIZE = 48 * 1024 * 1024  # 48 MB
