import base64
import hashlib
from datetime import timezone

from cryptography.fernet import Fernet
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from config import Config
from extensions import db
from models import OAuthToken, utcnow


def _fernet():
    digest = hashlib.sha256(Config.SECRET_KEY.encode()).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_value(value):
    if not value:
        return None
    return _fernet().encrypt(value.encode()).decode()


def decrypt_value(value):
    if not value:
        return None
    return _fernet().decrypt(value.encode()).decode()


def _normalize_expiry(expiry):
    if expiry is None:
        return None
    if expiry.tzinfo is not None:
        expiry = expiry.astimezone(timezone.utc).replace(tzinfo=None)
    return expiry


def save_credentials(email, credentials):
    token = OAuthToken.query.filter_by(email=email.lower()).first()
    if not token:
        token = OAuthToken(email=email.lower())
        db.session.add(token)

    token.access_token_enc = encrypt_value(credentials.token)
    token.refresh_token_enc = encrypt_value(credentials.refresh_token)
    token.token_expiry = _normalize_expiry(credentials.expiry)
    token.updated_at = utcnow()
    db.session.commit()
    return token


def load_credentials(email):
    token = OAuthToken.query.filter_by(email=email.lower()).first()
    if not token:
        return None

    credentials = Credentials(
        token=decrypt_value(token.access_token_enc),
        refresh_token=decrypt_value(token.refresh_token_enc),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=Config.GOOGLE_CLIENT_ID,
        client_secret=Config.GOOGLE_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    )
    credentials.expiry = _normalize_expiry(token.token_expiry)

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        save_credentials(email, credentials)

    return credentials


def has_connected_account():
    return OAuthToken.query.filter_by(email=Config.ALLOWED_USER_EMAIL).first() is not None
