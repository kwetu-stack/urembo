from google_auth_oauthlib.flow import Flow
from config import Config


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly"
]


def create_gmail_flow():
    client_config = {
        "web": {
            "client_id": Config.GOOGLE_CLIENT_ID,
            "client_secret": Config.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [
                f"{Config.BASE_URL}/email/oauth2callback"
            ]
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=f"{Config.BASE_URL}/email/oauth2callback"
    )

    return flow