from flask import Blueprint, redirect, render_template, request, session, url_for
from oauthlib.oauth2.rfc6749.errors import OAuth2Error

from config import Config
from services.gmail_service import create_gmail_flow
from services.sync_service import sync_gmail_reports
from services.token_store import has_connected_account, save_credentials

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/")
def home():
    if has_connected_account():
        session["connected"] = True
        session["user_email"] = Config.ALLOWED_USER_EMAIL
        return redirect(url_for("dashboard.dashboard"))
    return render_template("connect.html")


@auth_bp.route("/email/connect")
def connect_gmail():
    flow = create_gmail_flow()
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )
    session["oauth_state"] = state
    session["code_verifier"] = flow.code_verifier
    return redirect(authorization_url)


@auth_bp.route("/email/oauth2callback")
def gmail_oauth2callback():
    if request.args.get("error"):
        return render_template(
            "connect.html",
            error=f"Gmail connection was cancelled: {request.args.get('error')}",
        ), 400

    expected_state = session.pop("oauth_state", None)
    code_verifier = session.pop("code_verifier", None)

    if not expected_state or expected_state != request.args.get("state"):
        return render_template("connect.html", error="Invalid OAuth session. Please try again."), 400

    if not code_verifier:
        return render_template("connect.html", error="OAuth session expired. Please try again."), 400

    flow = create_gmail_flow()
    flow.code_verifier = code_verifier

    try:
        flow.fetch_token(authorization_response=request.url, state=expected_state)
    except OAuth2Error as exc:
        return render_template(
            "connect.html",
            error=f"Gmail connection failed: {exc.description or exc.error}",
        ), 400

    credentials = flow.credentials
    if not credentials or not credentials.token:
        return render_template("connect.html", error="No credentials received."), 400

    profile = None
    try:
        from googleapiclient.discovery import build
        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        profile = service.users().getProfile(userId="me").execute()
    except Exception:
        profile = None

    email = (profile or {}).get("emailAddress", Config.ALLOWED_USER_EMAIL).lower()
    if email != Config.ALLOWED_USER_EMAIL:
        return render_template(
            "connect.html",
            error=f"Only {Config.ALLOWED_USER_EMAIL} is allowed to connect.",
        ), 403

    save_credentials(email, credentials)
    session["connected"] = True
    session["user_email"] = email

    from flask import current_app
    sync_gmail_reports(current_app._get_current_object())

    return redirect(url_for("dashboard.dashboard"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.home"))
