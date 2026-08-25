import re
from datetime import datetime
from io import BytesIO

import pandas as pd
from bs4 import BeautifulSoup


def _clean_number(value):
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"nan", "none", "-"}:
        return None
    text = text.replace("%", "")
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return None


def _parse_report_date(subject, fallback=None):
    subject = subject or ""
    patterns = [
        r"AS AT (\d{1,2})(?:ST|ND|RD|TH)?\s+([A-Z]+)\s+(\d{4})",
        r"AS OF[_\s-]*(\d{2})-(\d{2})-(\d{4})",
        r"(\d{2})-(\d{2})-(\d{4})",
    ]
    months = {
        "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4,
        "MAY": 5, "JUNE": 6, "JULY": 7, "AUGUST": 8,
        "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
    }
    upper = subject.upper()
    match = re.search(patterns[0], upper)
    if match:
        day, month_name, year = match.groups()
        month = months.get(month_name[:3] if len(month_name) > 3 else month_name)
        if not month and month_name in months:
            month = months[month_name]
        if month:
            return datetime(int(year), month, int(day)).date()

    for pattern in patterns[1:]:
        match = re.search(pattern, subject)
        if match:
            d, m, y = match.groups()
            return datetime(int(y), int(m), int(d)).date()

    return fallback.date() if fallback else None


def _table_rows(soup):
    rows = []
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["td", "th"])]
            if cells:
                rows.append(cells)
    return rows


def parse_partner_performance_html(html, subject, received_at=None):
    soup = BeautifulSoup(html or "", "html.parser")
    text = soup.get_text("\n", strip=True)

    contract_status = None
    status_match = re.search(r"Signed Contract Status:\s*(.+)", text, re.I)
    if status_match:
        contract_status = status_match.group(1).strip()

    metrics = {}
    label_map = {
        "partner gross adds": "partner_gross_adds",
        "sim kits billing": "sim_kits_billing",
        "% active agents": "active_agents_pct",
        "back margin rate": "back_margin_rate",
        "primaries purchased": "primaries_purchased",
        "agent led airtime (direct)": "agent_led_airtime",
        "retailer influenced self recharges": "retailer_influenced_recharges",
        "total airtime": "total_airtime",
        "projected back margin commission": "projected_commission",
        "total agents in cluster": "total_agents_cluster",
        "agents served with 1k + & 5txn": "agents_served_1k_5txn",
        "agents served with 1k+ & 5txn": "agents_served_1k_5txn",
    }

    for row in _table_rows(soup):
        if not row:
            continue
        label = row[0].lower().strip()
        for key, field in label_map.items():
            if key in label:
                value = _clean_number(row[1]) if len(row) > 1 else None
                if field == "back_margin_rate" and value and value > 10:
                    value = value / 100 if value <= 100 else value
                metrics[field] = value
                if len(row) > 2 and field != "back_margin_rate":
                    margin = _clean_number(row[2])
                    if margin is not None and field.endswith("_pct") is False:
                        metrics.setdefault("back_margin_rate", margin)

    for label, field in label_map.items():
        if field in metrics:
            continue
        pattern = re.compile(rf"{re.escape(label)}\s*([\d,\.%]+)", re.I)
        match = pattern.search(text)
        if match:
            metrics[field] = _clean_number(match.group(1))

    return {
        "report_date": _parse_report_date(subject, received_at),
        "contract_status": contract_status,
        **metrics,
    }


def parse_sim_utilization_excel(file_bytes, subject, received_at=None):
    df = pd.read_excel(BytesIO(file_bytes), sheet_name=0, header=0)
    df.columns = [str(c).strip().lower() for c in df.columns]

    records = []
    for _, row in df.iterrows():
        activation = row.get("activation_time")
        records.append({
            "item_serial_number": str(row.get("item_serial_number", "")).strip(),
            "distributor_name": str(row.get("distributorname", "")).strip(),
            "order_date": pd.to_datetime(row.get("orderdate"), errors="coerce"),
            "kyc_msisdn": str(row.get("kyc_msisdn", "")).strip(),
            "served_msisdn": str(row.get("servedmsisdn", "")).strip(),
            "kyc_created_on": pd.to_datetime(row.get("kyc_createdon"), errors="coerce"),
            "activation_time": pd.to_datetime(activation, errors="coerce"),
            "device_technology": str(row.get("devicetechnology", "")).strip(),
            "recharge_amount": _clean_number(row.get("rechargeamount")),
            "retailer_msisdn": str(row.get("retailer_msisdn", "")).strip(),
            "zone_name": str(row.get("zone_name", "")).strip(),
        })

    total = len(records)
    activated = sum(1 for r in records if pd.notna(r["activation_time"]))
    utilization = round((activated / total) * 100, 2) if total else 0.0

    dso_id = str(df.iloc[0].get("dsoid", "")) if not df.empty else None
    distributor = str(df.iloc[0].get("distributorname", "")) if not df.empty else None

    return {
        "report_date": _parse_report_date(subject, received_at),
        "dso_id": dso_id,
        "distributor_name": distributor,
        "total_sims": total,
        "activated_sims": activated,
        "utilization_rate": utilization,
        "records": records,
    }


def parse_tudor_agents_excel(file_bytes, subject, received_at=None):
    df = pd.read_excel(BytesIO(file_bytes), sheet_name=0, header=2)
    df.columns = [str(c).strip().upper() for c in df.columns]

    agents = []
    for _, row in df.iterrows():
        agent_id = str(row.get("AGENT", "")).strip()
        if not agent_id or agent_id.lower() == "nan":
            continue
        agents.append({
            "agent_id": agent_id,
            "agent_name": str(row.get("AGENT NAME", "")).strip(),
            "site": str(row.get("SITE", "")).strip(),
            "tse": str(row.get("TSE", "")).strip(),
            "ama_1plus": str(row.get("AMA 1+", "")).strip().upper(),
            "qama": str(row.get("QAMA", "")).strip().upper(),
            "qdrso": str(row.get("QDRSO", "")).strip().upper(),
            "agent_status": str(row.get("AGENT STATUS", "")).strip(),
        })

    active = sum(1 for a in agents if a["agent_status"].lower() == "active")
    ama = sum(1 for a in agents if a["ama_1plus"] == "YES")
    qama = sum(1 for a in agents if a["qama"] == "YES")

    return {
        "report_date": _parse_report_date(subject, received_at),
        "total_agents": len(agents),
        "active_agents": active,
        "ama_1plus_count": ama,
        "qama_count": qama,
        "agents": agents,
    }
