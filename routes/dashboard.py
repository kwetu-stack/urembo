from functools import wraps

from flask import (
    Blueprint,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
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


@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    data = get_dashboard_data()
    return render_template("dashboard.html", **data)


@dashboard_bp.route("/sim-utilization")
@login_required
def sim_utilization():
    data = get_sim_utilization_page()
    return render_template("sim_utilization.html", **data)


@dashboard_bp.route("/partner-performance")
@login_required
def partner_performance():
    data = get_partner_performance_page()
    return render_template("partner_performance.html", **data)


@dashboard_bp.route("/agents")
@login_required
def agents():
    data = get_agents_page(
        search=request.args.get("q", "").strip() or None,
        status=request.args.get("status", "").strip() or None,
        page=request.args.get("page", 1, type=int),
    )
    return render_template("agents.html", **data)


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
            "sim_utilization": data["sim"].utilization_rate if data["sim"] else None,
            "total_sims": data["sim"].total_sims if data["sim"] else None,
            "active_agents": data["tudor"].active_agents if data["tudor"] else None,
            "alerts": data["alerts"],
            "commission_trend": data["commission_trend"],
            "utilization_trend": data["utilization_trend"],
        }
    )


@dashboard_bp.route("/api/diagnostics")
@login_required
def api_diagnostics():
    """What sync has stored, and how Tudor-looking mail in the inbox would be classified."""
    synced = SyncedEmail.query.order_by(SyncedEmail.received_at.desc()).limit(25).all()
    app = current_app._get_current_object()

    def scan(label, fn):
        try:
            return fn(app)
        except Exception:
            current_app.logger.exception("%s scan failed", label)
            return {"error": f"{label} scan failed", "messages": []}

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
                        email.received_at.isoformat() if email.received_at else None
                    ),
                    "report_type": email.report_type,
                }
                for email in synced
            ],
            "tudor_inbox_scan": tudor_scan,
            "attachment_scan": attachment_scan,
        }
    )


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
                    "error": "Sync failed. Please try again or contact support if it keeps happening.",
                }
            ),
            500,
        )
