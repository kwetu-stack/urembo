from datetime import datetime, timezone

from extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class OAuthToken(db.Model):
    __tablename__ = "oauth_tokens"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    access_token_enc = db.Column(db.Text, nullable=False)
    refresh_token_enc = db.Column(db.Text, nullable=True)
    token_expiry = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SyncedEmail(db.Model):
    __tablename__ = "synced_emails"

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    subject = db.Column(db.String(500))
    sender = db.Column(db.String(255))
    received_at = db.Column(db.DateTime(timezone=True))
    report_type = db.Column(db.String(50), nullable=False)
    processed_at = db.Column(db.DateTime(timezone=True), default=utcnow)


class PartnerPerformanceReport(db.Model):
    __tablename__ = "partner_performance_reports"

    id = db.Column(db.Integer, primary_key=True)
    synced_email_id = db.Column(db.Integer, db.ForeignKey("synced_emails.id"), unique=True)
    report_date = db.Column(db.Date, index=True)
    contract_status = db.Column(db.String(255))

    partner_gross_adds = db.Column(db.Integer)
    sim_kits_billing = db.Column(db.Integer)
    active_agents_pct = db.Column(db.Float)
    back_margin_rate = db.Column(db.Float)

    primaries_purchased = db.Column(db.Integer)
    agent_led_airtime = db.Column(db.Integer)
    retailer_influenced_recharges = db.Column(db.Integer)
    total_airtime = db.Column(db.Integer)
    projected_commission = db.Column(db.Float)

    total_agents_cluster = db.Column(db.Integer)
    agents_served_1k_5txn = db.Column(db.Integer)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    synced_email = db.relationship("SyncedEmail", backref=db.backref("partner_report", uselist=False))


class SimUtilizationReport(db.Model):
    __tablename__ = "sim_utilization_reports"

    id = db.Column(db.Integer, primary_key=True)
    synced_email_id = db.Column(db.Integer, db.ForeignKey("synced_emails.id"), unique=True)
    report_date = db.Column(db.Date, index=True)
    dso_id = db.Column(db.String(50))
    distributor_name = db.Column(db.String(255))

    total_sims = db.Column(db.Integer, default=0)
    activated_sims = db.Column(db.Integer, default=0)
    utilization_rate = db.Column(db.Float, default=0.0)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    synced_email = db.relationship("SyncedEmail", backref=db.backref("sim_report", uselist=False))
    records = db.relationship("SimUtilizationRecord", back_populates="report", cascade="all, delete-orphan")


class SimUtilizationRecord(db.Model):
    __tablename__ = "sim_utilization_records"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("sim_utilization_reports.id"), index=True)

    item_serial_number = db.Column(db.String(100))
    distributor_name = db.Column(db.String(255))
    order_date = db.Column(db.DateTime(timezone=True))
    kyc_msisdn = db.Column(db.String(20))
    served_msisdn = db.Column(db.String(20))
    kyc_created_on = db.Column(db.DateTime(timezone=True))
    activation_time = db.Column(db.DateTime(timezone=True))
    device_technology = db.Column(db.String(20))
    recharge_amount = db.Column(db.Float)
    retailer_msisdn = db.Column(db.String(20))
    zone_name = db.Column(db.String(50))

    report = db.relationship("SimUtilizationReport", back_populates="records")


class TudorAgentReport(db.Model):
    __tablename__ = "tudor_agent_reports"

    id = db.Column(db.Integer, primary_key=True)
    synced_email_id = db.Column(db.Integer, db.ForeignKey("synced_emails.id"), unique=True)
    report_date = db.Column(db.Date, index=True)

    total_agents = db.Column(db.Integer, default=0)
    active_agents = db.Column(db.Integer, default=0)
    ama_1plus_count = db.Column(db.Integer, default=0)
    qama_count = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    synced_email = db.relationship("SyncedEmail", backref=db.backref("tudor_report", uselist=False))
    agents = db.relationship("TudorAgent", back_populates="report", cascade="all, delete-orphan")


class TudorAgent(db.Model):
    __tablename__ = "tudor_agents"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("tudor_agent_reports.id"), index=True)

    agent_id = db.Column(db.String(50))
    agent_name = db.Column(db.String(255))
    site = db.Column(db.String(255))
    tse = db.Column(db.String(255))
    ama_1plus = db.Column(db.String(10))
    qama = db.Column(db.String(10))
    qdrso = db.Column(db.String(10))
    agent_status = db.Column(db.String(50))

    report = db.relationship("TudorAgentReport", back_populates="agents")
