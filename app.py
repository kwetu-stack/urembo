from flask import Flask, redirect, request, session
from werkzeug.middleware.proxy_fix import ProxyFix
from oauthlib.oauth2.rfc6749.errors import OAuth2Error
from config import Config
from services.gmail_service import create_gmail_flow

app = Flask(__name__)
app.config.from_object(Config)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)


@app.route("/")
def home():
    return """
    <h1>UREMBO</h1>
    <p>Email Intelligence Platform</p>

    <a href="/email/connect">Connect Joyce's Gmail Account</a>
    """


@app.route("/email/connect")
def connect_gmail():
    flow = create_gmail_flow()

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )

    session["oauth_state"] = state
    session["code_verifier"] = flow.code_verifier

    return redirect(authorization_url)


@app.route("/email/oauth2callback")
def gmail_oauth2callback():
    if request.args.get("error"):
        return (
            f"Gmail connection was cancelled or denied: {request.args.get('error')}. "
            "Please try again.",
            400,
        )

    expected_state = session.pop("oauth_state", None)
    code_verifier = session.pop("code_verifier", None)

    if not expected_state or expected_state != request.args.get("state"):
        return "Invalid OAuth session. Please go back and connect Gmail again.", 400

    if not code_verifier:
        return "OAuth session expired. Please go back and connect Gmail again.", 400

    flow = create_gmail_flow()
    flow.code_verifier = code_verifier

    try:
        flow.fetch_token(
            authorization_response=request.url,
            state=expected_state,
        )
    except OAuth2Error as exc:
        return f"Gmail connection failed: {exc.description or exc.error}. Please try again.", 400

    credentials = flow.credentials

    if not credentials or not credentials.token:
        return "Gmail connection failed: no credentials received. Please try again.", 400

    return "Gmail connected successfully."


if __name__ == "__main__":
    app.run(debug=True)
