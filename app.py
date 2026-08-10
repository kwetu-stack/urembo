from flask import Flask, redirect
from config import Config
from services.gmail_service import create_gmail_flow

app = Flask(__name__)
app.config.from_object(Config)


@app.route("/")
def home():
    return "UREMBO is running successfully."


@app.route("/email/connect")
def connect_gmail():
    flow = create_gmail_flow()

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent"
    )

    return redirect(authorization_url)


if __name__ == "__main__":
    app.run(debug=True)