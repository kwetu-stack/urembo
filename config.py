import os
from dotenv import load_dotenv

load_dotenv()


def _database_url():
    url = os.getenv("DATABASE_URL", "sqlite:///urembo.db")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-production")

    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

    BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:5000")

    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SESSION_COOKIE_SECURE = BASE_URL.startswith("https://")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    SYNC_INTERVAL_MINUTES = int(os.getenv("SYNC_INTERVAL_MINUTES", "60"))
    ALLOWED_USER_EMAIL = os.getenv(
        "ALLOWED_USER_EMAIL", "joycegachoki74@gmail.com"
    ).lower()

    AIRTEL_SENDER_DOMAINS = ("ke.airtel.com", "airtel.com", "kwetupartners.net")
    ALLOWED_SENDERS = (
        "a_lamek.omullo@ke.airtel.com",
        "a_david.kemboi@ke.airtel.com",
        "a_rebecca.wanjiru@ke.airtel.com",
        "a_dan.rotich@ke.airtel.com",
    )
