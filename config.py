import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
FIREBASE_DB_URL: str = os.getenv("FIREBASE_DB_URL", "")
FIREBASE_AUTH_SECRET: str = os.getenv("FIREBASE_AUTH_SECRET", "")
CAPTCHA_ATTEMPTS: int = int(os.getenv("CAPTCHA_ATTEMPTS", "3"))

CLIENT_FILE: str = os.getenv("CLIENT_FILE", "")

_raw_admins = os.getenv("ADMIN_IDS", "8711035827").replace(" ", "")
ADMIN_IDS: set[int] = {int(x) for x in _raw_admins.split(",") if x}


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS
