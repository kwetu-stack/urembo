from functools import wraps
from io import BytesIO
from openpyxl import Workbook

from flask import (
    Blueprint,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
    send_file,
)
from config import Config
from models import (
    PartnerPerformanceReport,
    SimUtilizationReport,
    SyncedEmail,
    TudorAgent,
    TudorAgentReport,
)

from services.analytics import (
    get_agents_page,
    get_dashboard_data,
    get_partner_performance_page,
    get_sim_utilization_page,
    get_tudor_summary,
    get_sim_verification,
)

from services.sync_service import (
    GMAIL_QUERY,
    _build_gmail_query,
    inspect_attachment_messages,
    inspect_tudor_messages,
    sync_gmail_reports,
)

from services.token_store import has_connected_account

dashboard_bp = Blueprint("dashboard", __name__)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("connected") or not has_connected_account():
            return redirect(url_for("auth.home"))
        return view(*args, **kwargs)

    return wrapped


# ======================================================
# DASHBOARD
# ======================================================

@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    data = get_dashboard_data()
    return render_template("dashboard.html", **data)


# ======================================================
# SIM UTILIZATION
# ======================================================

@dashboard_bp.route("/sim-utilization")
@login_required
def sim_utilization():
    data = get_sim_utilization_page()
    return render_template("sim_utilization.html", **data)


# ======================================================
# SIM VERIFICATION
# ======================================================

@dashboard_bp.route("/sim-verification")
@login_required
def sim_verification():

    retailer = request.args.get("retailer", "").strip()
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")

    data = get_sim_verification(
        retailer_msisdn=retailer if retailer else None,
        start_date=start_date if start_date else None,
        end_date=end_date if end_date else None,
    )

    return render_template(
        "sim_verification.html",
        **data,
    )


# ======================================================
# EXPORT SIM VERIFICATION TO EXCEL
# ======================================================

@dashboard_bp.route("/sim-verification/export")
@login_required
def export_sim_verification():

    retailer = request.args.get("retailer", "").strip()
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")

    data = get_sim_verification(
        retailer_msisdn=retailer if retailer else None,
        start_date=start_date if start_date else None,
        end_date=end_date if end_date else None,
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "SIM Verification"

    # Report Header
    ws.append(["SIM VERIFICATION REPORT"])
    ws.append([])
    ws.append(["Retailer MSISDN", retailer])
    ws.append(["From", start_date])
    ws.append(["To", end_date])
    ws.append(["Activated SIMs", data["claimable_sims"]])
    ws.append(["Rate per SIM", data["claim_rate"]])
    ws.append(["Claimable Amount", data["claim_amount"]])
    ws.append([])

    # Table Header
    ws.append([
        "Serial Number",
        "Served MSISDN",
        "Activation Time",
        "Recharge",
        "Zone"
    ])

    # Data
    for sim in data["records"]:
        ws.append([
            sim.item_serial_number,
            sim.served_msisdn,
            sim.activation_time.strftime("%Y-%m-%d %H:%M") if sim.activation_time else "",
            sim.recharge_amount,
            sim.zone_name,
        ])

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"SIM_Claim_{retailer}.xlsx"

    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
# ======================================================
# PARTNER PERFORMANCE
# ======================================================

@dashboard_bp.route("/partner-performance")
@login_required
def partner_performance():
    data = get_partner_performance_page()
    return render_template("partner_performance.html", **data)


# ======================================================
# AGENTS
# ======================================================

@dashboard_bp.route("/agents")
@login_required
def agents():
    data = get_agents_page(
        search=request.args.get("q", "").strip() or None,
        status=request.args.get("status", "").strip() or None,
        page=request.args.get("page", 1, type=int),
    )
    return render_template("agents.html", **data)


# ======================================================
# API - DASHBOARD
# ======================================================

@dashboard_bp.route("/api/dashboard")
@login_required
def api_dashboard():
    data = get_dashboard_data()

    return jsonify(
        {
            "commission": (
                data["partner"].projected_commission if data["partner"] else None
            ),
            "contract_status": (
                data["partner"].contract_status if data["partner"] else None
            ),
            "sim_utilization": (
                data["sim"].utilization_rate if data["sim"] else None
            ),
            "total_sims": (
                data["sim"].total_sims if data["sim"] else None
            ),
            "active_agents": (
                data["tudor"].active_agents if data["tudor"] else None
            ),
            "alerts": data["alerts"],
            "commission_trend": data["commission_trend"],
            "utilization_trend": data["utilization_trend"],
        }
    )


# ======================================================
# API - DIAGNOSTICS
# ======================================================

@dashboard_bp.route("/api/diagnostics")
@login_required
def api_diagnostics():

    synced = (
        SyncedEmail.query
        .order_by(SyncedEmail.received_at.desc())
        .limit(25)
        .all()
    )

    app = current_app._get_current_object()

    def scan(label, fn):
        try:
            return fn(app)
        except Exception:
            current_app.logger.exception("%s scan failed", label)
            return {
                "error": f"{label} scan failed",
                "messages": [],
            }

    tudor_scan = scan("Tudor inbox", inspect_tudor_messages)
    attachment_scan = scan("Attachment", inspect_attachment_messages)

    return jsonify(
        {
            "gmail_query": _build_gmail_query(),
            "allowed_sender_domains": Config.AIRTEL_SENDER_DOMAINS,
            "allowed_senders": Config.ALLOWED_SENDERS,
            "counts": {
                "synced_emails": SyncedEmail.query.count(),
                "partner_performance_reports": PartnerPerformanceReport.query.count(),
                "sim_utilization_reports": SimUtilizationReport.query.count(),
                "tudor_agent_reports": TudorAgentReport.query.count(),
                "tudor_agents": TudorAgent.query.count(),
            },
            "recent_synced_emails": [
                {
                    "subject": email.subject,
                    "sender": email.sender,
                    "received_at": (
                        email.received_at.isoformat()
                        if email.received_at
                        else None
                    ),
                    "report_type": email.report_type,
                }
                for email in synced
            ],
            "tudor_inbox_scan": tudor_scan,
            "attachment_scan": attachment_scan,
        }
    )


# ======================================================
# API - MANUAL SYNC
# ======================================================

@dashboard_bp.route("/api/sync", methods=["POST"])
@login_required
def api_sync():
    try:
        result = sync_gmail_reports(current_app._get_current_object())
        return jsonify(result)

    except Exception:
        current_app.logger.exception("Gmail sync failed")

        return (
            jsonify(
                {
                    "processed": 0,
                    "failed": 0,
                    "error": (
                        "Sync failed. Please try again "
                        "or contact support if it keeps happening."
                    ),
                }
            ),
            500,
        )