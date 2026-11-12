"""Building blocks for the two plays. Pure functions: records in, plain dicts out."""
from __future__ import annotations

import datetime as dt

from . import config

ROLE_WEIGHT = {"exec_sponsor": 3, "champion": 3, "power_user": 2, "admin": 1}
ROLE_TEXT = {"exec_sponsor": "executive sponsor", "champion": "champion", "power_user": "power user",
             "admin": "admin"}


def risk_level(days: int) -> str:
    if days <= config.RISK_HIGH_DAYS:
        return "high"
    if days <= config.RISK_MEDIUM_DAYS:
        return "medium"
    return "low"


def next_best_contacts(departed: dict, account_contacts: list[dict], event_date: dt.date, n: int = 3) -> list[dict]:
    ranked = []
    for c in account_contacts:
        if c["id"] == departed["id"]:
            continue
        idle = (event_date - dt.date.fromisoformat(c["last_active_date"])).days
        score = ROLE_WEIGHT[c["role"]] + (1 if idle <= 14 else 0) + min(c["boards_created"], 60) / 120
        reason = f"{ROLE_TEXT[c['role']]}, {c['boards_created']} boards created, last active {idle} days before the event"
        ranked.append((score, c, reason))
    ranked.sort(key=lambda t: (-t[0], t[1]["id"]))
    return [{"contact_id": c["id"], "name": c["full_name"], "role": c["role"], "title": c["title"],
             "reason": reason} for _, c, reason in ranked[:n]]


def build_risk_flag(flag_id: str, event: dict, departed: dict, account: dict, others: list[dict]) -> dict:
    received = dt.date.fromisoformat(event["received_at"])
    days = (dt.date.fromisoformat(account["renewal_date"]) - received).days
    level = risk_level(days)
    return {"id": flag_id, "type": "risk_flag", "event_id": event["event_id"], "account_id": account["id"],
            "account_name": account["name"], "plan": account["plan"], "arr": account["arr"],
            "departed_contact_id": departed["id"], "departed_name": departed["full_name"],
            "departed_role": departed["role"], "days_until_renewal": days, "renewal_date": account["renewal_date"],
            "risk_level": level, "next_best_contacts": next_best_contacts(departed, others, received),
            "summary": f"{departed['full_name']} ({ROLE_TEXT[departed['role']]}) left {account['name']}; "
                       f"renewal in {days} days."}


def build_csm_task(task_id: str, flag: dict, account: dict, received_at: str) -> dict:
    due = dt.date.fromisoformat(received_at) + dt.timedelta(days=2)
    return {"id": task_id, "type": "csm_task", "event_id": flag["event_id"], "flag_id": flag["id"],
            "assignee": account["csm"], "account_id": account["id"], "due": due.isoformat(),
            "title": f"Confirm who the new champion is at {account['name']}",
            "detail": flag["summary"]}
