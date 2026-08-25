from sqlalchemy import case, desc, func

from models import (
    PartnerPerformanceReport,
    SimUtilizationReport,
    TudorAgent,
    TudorAgentReport,
)


def _latest(model, date_field="report_date"):
    return model.query.order_by(desc(getattr(model, date_field)), desc(model.id)).first()


def get_dashboard_data():
    partner = _latest(PartnerPerformanceReport)
    sim = _latest(SimUtilizationReport)
    tudor = _latest(TudorAgentReport)

    partner_history = (
        PartnerPerformanceReport.query
        .order_by(PartnerPerformanceReport.report_date.asc())
        .all()
    )
    sim_history = (
        SimUtilizationReport.query
        .order_by(SimUtilizationReport.report_date.asc())
        .all()
    )

    top_agents = []
    if tudor:
        top_agents = (
            TudorAgent.query
            .filter_by(report_id=tudor.id, agent_status="Active")
            .filter(TudorAgent.ama_1plus == "YES")
            .order_by(TudorAgent.agent_name.asc())
            .limit(10)
            .all()
        )

    alerts = []
    if partner and partner.contract_status:
        status = partner.contract_status.upper()
        if "PARTIAL" in status or "PENDING" in status:
            alerts.append({
                "level": "warning",
                "message": f"Contract status: {partner.contract_status}",
            })

    if sim and sim.utilization_rate < 50:
        alerts.append({
            "level": "danger",
            "message": f"SIM utilization is low at {sim.utilization_rate}%",
        })
    elif sim and sim.utilization_rate < 70:
        alerts.append({
            "level": "warning",
            "message": f"SIM utilization could improve: {sim.utilization_rate}%",
        })

    if tudor:
        inactive = tudor.total_agents - tudor.active_agents
        if inactive > 0:
            alerts.append({
                "level": "info",
                "message": f"{inactive} Tudor agents are inactive",
            })

    return {
        "partner": partner,
        "sim": sim,
        "tudor": tudor,
        "top_agents": top_agents,
        "alerts": alerts,
        "commission_trend": [
            {
                "date": r.report_date.isoformat() if r.report_date else None,
                "commission": r.projected_commission or 0,
                "gross_adds": r.partner_gross_adds or 0,
            }
            for r in partner_history
        ],
        "utilization_trend": [
            {
                "date": r.report_date.isoformat() if r.report_date else None,
                "rate": r.utilization_rate or 0,
                "total": r.total_sims or 0,
                "activated": r.activated_sims or 0,
            }
            for r in sim_history
        ],
    }


def get_partner_performance_page():
    reports = PartnerPerformanceReport.query.order_by(
        desc(PartnerPerformanceReport.report_date),
        desc(PartnerPerformanceReport.id),
    ).all()
    latest = reports[0] if reports else None
    return {"reports": reports, "latest": latest}


def get_sim_utilization_page():
    reports = SimUtilizationReport.query.order_by(
        desc(SimUtilizationReport.report_date),
        desc(SimUtilizationReport.id),
    ).all()
    latest = reports[0] if reports else None

    zone_breakdown = []
    retailer_breakdown = []
    if latest:
        from models import SimUtilizationRecord

        zone_rows = (
            SimUtilizationRecord.query
            .filter_by(report_id=latest.id)
            .with_entities(
                SimUtilizationRecord.zone_name,
                func.count(SimUtilizationRecord.id),
                func.sum(case((SimUtilizationRecord.activation_time.isnot(None), 1), else_=0)),
            )
            .group_by(SimUtilizationRecord.zone_name)
            .all()
        )
        zone_breakdown = [
            {
                "zone": row[0] or "Unknown",
                "total": row[1],
                "activated": int(row[2] or 0),
            }
            for row in zone_rows
        ]

        retailer_rows = (
            SimUtilizationRecord.query
            .filter_by(report_id=latest.id)
            .with_entities(
                SimUtilizationRecord.retailer_msisdn,
                func.count(SimUtilizationRecord.id),
            )
            .group_by(SimUtilizationRecord.retailer_msisdn)
            .order_by(desc(func.count(SimUtilizationRecord.id)))
            .limit(10)
            .all()
        )
        retailer_breakdown = [
            {"retailer": row[0] or "Unknown", "count": row[1]}
            for row in retailer_rows
        ]

    return {
        "reports": reports,
        "latest": latest,
        "zone_breakdown": zone_breakdown,
        "retailer_breakdown": retailer_breakdown,
    }


def get_tudor_summary():
    latest = _latest(TudorAgentReport)
    if not latest:
        return {"latest": None, "agents": []}

    agents = (
        TudorAgent.query
        .filter_by(report_id=latest.id)
        .order_by(TudorAgent.agent_name.asc())
        .limit(100)
        .all()
    )
    return {"latest": latest, "agents": agents}
