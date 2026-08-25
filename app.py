import os
from datetime import datetime

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
        _seed_sample_reports(app)

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


def _seed_sample_reports(app):
    if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        return
    if os.getenv("SEED_SAMPLE_DATA", "true").lower() != "true":
        return

    from models import (
        PartnerPerformanceReport,
        SimUtilizationRecord,
        SimUtilizationReport,
        SyncedEmail,
        TudorAgent,
        TudorAgentReport,
    )
    from services.parsers import parse_sim_utilization_excel, parse_tudor_agents_excel

    if PartnerPerformanceReport.query.first():
        return

    base = os.path.join(app.root_path, "AIRTEL REPORTS")
    if not os.path.isdir(base):
        return

    now = datetime.utcnow()

    partner_email = SyncedEmail(
        message_id="seed-partner-performance",
        subject="PARTNER PERFORMANCE REPORT AS AT 16TH JULY 2026",
        sender="a_lamek.omullo@ke.airtel.com",
        received_at=now,
        report_type="partner_performance",
    )
    db.session.add(partner_email)
    db.session.flush()
    db.session.add(PartnerPerformanceReport(
        synced_email_id=partner_email.id,
        report_date=datetime(2026, 7, 16).date(),
        contract_status="PARTIAL DOCUMENTS SHARED",
        partner_gross_adds=583,
        sim_kits_billing=1250,
        active_agents_pct=81,
        back_margin_rate=1.75,
        primaries_purchased=95000,
        agent_led_airtime=20254,
        retailer_influenced_recharges=88360,
        total_airtime=203614,
        projected_commission=3563,
        total_agents_cluster=75,
        agents_served_1k_5txn=61,
    ))

    sim_path = os.path.join(base, "1140749_SIM Insuance and Utilization Report as of_07-05-2026 (2).xlsx")
    if os.path.exists(sim_path):
        with open(sim_path, "rb") as handle:
            parsed = parse_sim_utilization_excel(handle.read(), os.path.basename(sim_path), now)
        sim_email = SyncedEmail(
            message_id="seed-sim-utilization",
            subject=os.path.basename(sim_path),
            sender="reports@ke.airtel.com",
            received_at=now,
            report_type="sim_utilization",
        )
        db.session.add(sim_email)
        db.session.flush()
        sim_report = SimUtilizationReport(
            synced_email_id=sim_email.id,
            report_date=parsed.get("report_date"),
            dso_id=parsed.get("dso_id"),
            distributor_name=parsed.get("distributor_name"),
            total_sims=parsed.get("total_sims", 0),
            activated_sims=parsed.get("activated_sims", 0),
            utilization_rate=parsed.get("utilization_rate", 0.0),
        )
        db.session.add(sim_report)
        db.session.flush()
        for record in parsed.get("records", [])[:500]:
            db.session.add(SimUtilizationRecord(
                report_id=sim_report.id,
                item_serial_number=record.get("item_serial_number"),
                distributor_name=record.get("distributor_name"),
                kyc_msisdn=record.get("kyc_msisdn"),
                served_msisdn=record.get("served_msisdn"),
                device_technology=record.get("device_technology"),
                recharge_amount=record.get("recharge_amount"),
                retailer_msisdn=record.get("retailer_msisdn"),
                zone_name=record.get("zone_name"),
            ))

    tudor_path = os.path.join(base, "TUDOR AGENTS (1).xlsx")
    if os.path.exists(tudor_path):
        with open(tudor_path, "rb") as handle:
            parsed = parse_tudor_agents_excel(handle.read(), os.path.basename(tudor_path), now)
        tudor_email = SyncedEmail(
            message_id="seed-tudor-agents",
            subject=os.path.basename(tudor_path),
            sender="reports@ke.airtel.com",
            received_at=now,
            report_type="tudor_agents",
        )
        db.session.add(tudor_email)
        db.session.flush()
        tudor_report = TudorAgentReport(
            synced_email_id=tudor_email.id,
            report_date=parsed.get("report_date"),
            total_agents=parsed.get("total_agents", 0),
            active_agents=parsed.get("active_agents", 0),
            ama_1plus_count=parsed.get("ama_1plus_count", 0),
            qama_count=parsed.get("qama_count", 0),
        )
        db.session.add(tudor_report)
        db.session.flush()
        for agent in parsed.get("agents", [])[:500]:
            db.session.add(TudorAgent(
                report_id=tudor_report.id,
                agent_id=agent.get("agent_id"),
                agent_name=agent.get("agent_name"),
                site=agent.get("site"),
                tse=agent.get("tse"),
                ama_1plus=agent.get("ama_1plus"),
                qama=agent.get("qama"),
                qdrso=agent.get("qdrso"),
                agent_status=agent.get("agent_status"),
            ))

    db.session.commit()


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
