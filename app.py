from flask import Flask, redirect, request, session
from config import Config
from services.gmail_service import create_gmail_flow

app = Flask(__name__)
app.config.from_object(Config)


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
        prompt="consent"
    )

    session["oauth_state"] = state

    return redirect(authorization_url)


@app.route("/email/oauth2callback")
def gmail_oauth2callback():
    flow = create_gmail_flow()

    flow.fetch_token(
        authorization_response=request.url
    )

    credentials = flow.credentials

    return "Gmail connected successfully."


if __name__ == "__main__":
    app.run(debug=True)