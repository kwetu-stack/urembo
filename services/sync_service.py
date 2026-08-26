import base64
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from flask import current_app
from googleapiclient.discovery import build

from config import Config
from extensions import db
from models import (
    PartnerPerformanceReport,
    SimUtilizationRecord,
    SimUtilizationReport,
    SyncedEmail,
    TudorAgent,
    TudorAgentReport,
    utcnow,
)
from services.parsers import (
    parse_partner_performance_html,
    parse_sim_utilization_excel,
    parse_tudor_agents_excel,
)
from services.token_store import load_credentials


GMAIL_QUERY = (
    'from:airtel.com OR from:ke.airtel.com OR from:kwetupartners.net OR '
    'subject:"PARTNER PERFORMANCE" OR subject:"SIM Insuance" OR '
    'subject:"SIM Issuance" OR subject:"TUDOR AGENTS" OR '
    'subject:TUDOR OR filename:TUDOR'
)


TUDOR_QUERY = 'subject:TUDOR OR filename:TUDOR OR subject:AGENT'

REPORT_MODELS = {
    "partner_performance": PartnerPerformanceReport,
    "sim_utilization": SimUtilizationReport,
    "tudor_agents": TudorAgentReport,
}


def _has_report(synced_email):
    """True when the stored email already produced its report row."""
    model = REPORT_MODELS.get(synced_email.report_type)
    if not model:
        return True
    return model.query.filter_by(synced_email_id=synced_email.id).first() is not None


def _naive(dt):
    if dt is None or dt != dt:
        return None
    if hasattr(dt, "to_pydatetime"):
        dt = dt.to_pydatetime()
    if not isinstance(dt, datetime):
        return None
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def get_gmail_service():
    credentials = load_credentials(Config.ALLOWED_USER_EMAIL)
    if not credentials:
        return None
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def _decode_body(part):
    data = part.get("body", {}).get("data")
    if not data:
        return ""
    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")


def _extract_parts(payload):
    html = ""
    text = ""
    attachments = []

    if not payload:
        return html, text, attachments

    mime = payload.get("mimeType", "")
    if mime == "text/html":
        html = _decode_body(payload)
    elif mime == "text/plain":
        text = _decode_body(payload)

    for part in payload.get("parts", []):
        part_mime = part.get("mimeType", "")
        filename = part.get("filename", "")

        if part.get("body", {}).get("attachmentId") and filename:
            attachments.append(part)
        elif part_mime == "text/html":
            html = html or _decode_body(part)
        elif part_mime == "text/plain":
            text = text or _decode_body(part)
        elif part_mime.startswith("multipart/"):
            nested_html, nested_text, nested_attachments = _extract_parts(part)
            html = html or nested_html
            text = text or nested_text
            attachments.extend(nested_attachments)

    return html, text, attachments


def _download_attachment(service, message_id, part):
    attachment_id = part["body"]["attachmentId"]
    attachment = service.users().messages().attachments().get(
        userId="me", messageId=message_id, id=attachment_id
    ).execute()
    return base64.urlsafe_b64decode(attachment["data"])


def _classify_message(subject, filenames):
    subject_upper = (subject or "").upper()
    names_upper = " ".join(filenames).upper()

    if "PARTNER PERFORMANCE" in subject_upper:
        return "partner_performance"
    if "SIM" in names_upper and ("UTILIZATION" in names_upper or "INSUANCE" in names_upper or "ISSUANCE" in names_upper):
        return "sim_utilization"
    if "TUDOR" in names_upper and "AGENT" in names_upper:
        return "tudor_agents"
    if "SIM" in subject_upper:
        return "sim_utilization"
    if "TUDOR" in subject_upper:
        return "tudor_agents"
    return None


def _sender_allowed(sender):
    sender = (sender or "").lower()
    return any(domain in sender for domain in Config.AIRTEL_SENDER_DOMAINS)


def _save_partner_report(synced_email, parsed):
    report = PartnerPerformanceReport(
        synced_email_id=synced_email.id,
        report_date=parsed.get("report_date"),
        contract_status=parsed.get("contract_status"),
        partner_gross_adds=parsed.get("partner_gross_adds"),
        sim_kits_billing=parsed.get("sim_kits_billing"),
        active_agents_pct=parsed.get("active_agents_pct"),
        back_margin_rate=parsed.get("back_margin_rate"),
        primaries_purchased=parsed.get("primaries_purchased"),
        agent_led_airtime=parsed.get("agent_led_airtime"),
        retailer_influenced_recharges=parsed.get("retailer_influenced_recharges"),
        total_airtime=parsed.get("total_airtime"),
        projected_commission=parsed.get("projected_commission"),
        total_agents_cluster=parsed.get("total_agents_cluster"),
        agents_served_1k_5txn=parsed.get("agents_served_1k_5txn"),
    )
    db.session.add(report)


def _save_sim_report(synced_email, parsed):
    report = SimUtilizationReport(
        synced_email_id=synced_email.id,
        report_date=parsed.get("report_date"),
        dso_id=parsed.get("dso_id"),
        distributor_name=parsed.get("distributor_name"),
        total_sims=parsed.get("total_sims", 0),
        activated_sims=parsed.get("activated_sims", 0),
        utilization_rate=parsed.get("utilization_rate", 0.0),
    )
    db.session.add(report)
    db.session.flush()

    for record in parsed.get("records", []):
        db.session.add(SimUtilizationRecord(
            report_id=report.id,
            item_serial_number=record.get("item_serial_number"),
            distributor_name=record.get("distributor_name"),
            order_date=_naive(record.get("order_date")),
            kyc_msisdn=record.get("kyc_msisdn"),
            served_msisdn=record.get("served_msisdn"),
            kyc_created_on=_naive(record.get("kyc_created_on")),
            activation_time=_naive(record.get("activation_time")),
            device_technology=record.get("device_technology"),
            recharge_amount=record.get("recharge_amount"),
            retailer_msisdn=record.get("retailer_msisdn"),
            zone_name=record.get("zone_name"),
        ))


def _save_tudor_report(synced_email, parsed):
    report = TudorAgentReport(
        synced_email_id=synced_email.id,
        report_date=parsed.get("report_date"),
        total_agents=parsed.get("total_agents", 0),
        active_agents=parsed.get("active_agents", 0),
        ama_1plus_count=parsed.get("ama_1plus_count", 0),
        qama_count=parsed.get("qama_count", 0),
    )
    db.session.add(report)
    db.session.flush()

    for agent in parsed.get("agents", []):
        db.session.add(TudorAgent(
            report_id=report.id,
            agent_id=agent.get("agent_id"),
            agent_name=agent.get("agent_name"),
            site=agent.get("site"),
            tse=agent.get("tse"),
            ama_1plus=agent.get("ama_1plus"),
            qama=agent.get("qama"),
            qdrso=agent.get("qdrso"),
            agent_status=agent.get("agent_status"),
        ))


def process_message(service, message):
    message_id = message["id"]
    existing = SyncedEmail.query.filter_by(message_id=message_id).first()
    if existing:
        if _has_report(existing):
            return False
        # Email was recorded by an earlier run that failed before saving its report;
        # drop the marker so the message is parsed again below.
        db.session.delete(existing)
        db.session.flush()

    full = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = {h["name"].lower(): h["value"] for h in full["payload"].get("headers", [])}
    subject = headers.get("subject", "")
    sender = headers.get("from", "")

    if not _sender_allowed(sender):
        return False

    received_at = utcnow()
    if headers.get("date"):
        try:
            received_at = parsedate_to_datetime(headers["date"])
            if received_at.tzinfo is None:
                received_at = received_at.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            pass

    html, text, attachment_parts = _extract_parts(full["payload"])
    filenames = [p.get("filename", "") for p in attachment_parts]
    report_type = _classify_message(subject, filenames)
    if not report_type:
        return False

    synced_email = SyncedEmail(
        message_id=message_id,
        subject=subject,
        sender=sender,
        received_at=received_at,
        report_type=report_type,
    )
    db.session.add(synced_email)
    db.session.flush()

    if report_type == "partner_performance":
        parsed = parse_partner_performance_html(html or text, subject, received_at)
        _save_partner_report(synced_email, parsed)
    elif report_type == "sim_utilization":
        excel_part = next(
            (p for p in attachment_parts if re.search(r"sim", p.get("filename", ""), re.I)),
            attachment_parts[0] if attachment_parts else None,
        )
        if not excel_part:
            db.session.rollback()
            return False
        file_bytes = _download_attachment(service, message_id, excel_part)
        parsed = parse_sim_utilization_excel(file_bytes, subject, received_at)
        _save_sim_report(synced_email, parsed)
    elif report_type == "tudor_agents":
        excel_part = attachment_parts[0] if attachment_parts else None
        if not excel_part:
            db.session.rollback()
            return False
        file_bytes = _download_attachment(service, message_id, excel_part)
        parsed = parse_tudor_agents_excel(file_bytes, subject, received_at)
        _save_tudor_report(synced_email, parsed)

    db.session.commit()
    return True


def sync_gmail_reports(app):
    with app.app_context():
        service = get_gmail_service()
        if not service:
            return {"processed": 0, "failed": 0, "error": "No connected Gmail account"}

        processed = 0
        failed = 0
        page_token = None
        while True:
            response = service.users().messages().list(
                userId="me",
                q=GMAIL_QUERY,
                maxResults=50,
                pageToken=page_token,
            ).execute()

            for message in response.get("messages", []):
                try:
                    if process_message(service, message):
                        processed += 1
                except Exception:
                    db.session.rollback()
                    failed += 1
                    current_app.logger.exception(
                        "Failed to process Gmail message %s", message.get("id")
                    )

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return {"processed": processed, "failed": failed, "error": None}


def inspect_tudor_messages(app, limit=25):
    """Report what Gmail returns for Tudor-looking mail and how sync would classify it."""
    with app.app_context():
        service = get_gmail_service()
        if not service:
            return {"error": "No connected Gmail account", "messages": []}

        response = service.users().messages().list(
            userId="me", q=TUDOR_QUERY, maxResults=limit
        ).execute()

        messages = []
        for message in response.get("messages", []):
            full = service.users().messages().get(
                userId="me", id=message["id"], format="full"
            ).execute()
            headers = {h["name"].lower(): h["value"] for h in full["payload"].get("headers", [])}
            subject = headers.get("subject", "")
            sender = headers.get("from", "")
            _, _, attachment_parts = _extract_parts(full["payload"])
            filenames = [p.get("filename", "") for p in attachment_parts]
            synced = SyncedEmail.query.filter_by(message_id=message["id"]).first()
            messages.append({
                "subject": subject,
                "sender": sender,
                "date": headers.get("date"),
                "filenames": filenames,
                "sender_allowed": _sender_allowed(sender),
                "classified_as": _classify_message(subject, filenames),
                "matches_sync_query": None,
                "already_synced": bool(synced),
                "has_report": _has_report(synced) if synced else False,
            })

        synced_ids = {
            m["id"] for m in service.users().messages().list(
                userId="me", q=GMAIL_QUERY, maxResults=500
            ).execute().get("messages", [])
        }
        for entry, message in zip(messages, response.get("messages", [])):
            entry["matches_sync_query"] = message["id"] in synced_ids

        return {"error": None, "messages": messages}
