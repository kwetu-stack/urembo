from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from extensions import db, scheduler
from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from services.sync_service import sync_gmail_reports


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    db.init_app(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)

    with app.app_context():
        db.create_all()
        purge_seeded_reports()

    if not scheduler.running:
        scheduler.add_job(
            func=lambda: sync_gmail_reports(app),
            trigger="interval",
            minutes=Config.SYNC_INTERVAL_MINUTES,
            id="gmail_sync",
            replace_existing=True,
        )
        scheduler.start()

    return app


def purge_seeded_reports():
    """Remove sample rows written by earlier releases so the dashboard only shows synced data."""
    from models import (
        PartnerPerformanceReport,
        SimUtilizationReport,
        SyncedEmail,
        TudorAgentReport,
    )

    seeded = SyncedEmail.query.filter(SyncedEmail.message_id.like("seed-%")).all()
    if not seeded:
        return

    seeded_ids = [email.id for email in seeded]
    for model in (PartnerPerformanceReport, SimUtilizationReport, TudorAgentReport):
        for report in model.query.filter(model.synced_email_id.in_(seeded_ids)).all():
            db.session.delete(report)
    for email in seeded:
        db.session.delete(email)
    db.session.commit()


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
