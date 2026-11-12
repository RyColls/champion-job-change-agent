"""Build docs/walkthrough.html: a guided trail through one event at a time.

All content comes from committed results files (results/<feed>/<backend>/) and the agent's own inputs
(data/<feed>/). Nothing under evals/keys is read. Run: python demo/walkthrough.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import config  # noqa: E402
from agent.rules import GUARDS, RULES  # noqa: E402

# Figures from the first measured run (git commit 2ee645e), kept so the before/after stays visible.
RUN1 = {1: "48 of 55", 2: "1 of 9", 3: "0 of 4", 4: "72 of 80 (90.0%)", 5: "0 drafts", 6: "48 of 55",
        7: "0 unsupported facts", 8: "nothing sent without a human", 9: "80 of 80"}
RUN1_PASS = {1: False, 2: False, 3: True, 4: False, 5: True, 6: False, 7: True, 8: True, 9: True}

# Outcome class per rule: drives pebble colour and the legend.
CLASS = {"R1": "draft", "R2": "flag", "R3": "flag", "R4": "flag", "R5": "flag", "R7": "flag",
         "R6": "update", "G3": "review", "G2": "ignored", "G1": "ignored"}

STEP_NAMES = {"normalize": "Read", "identity": "Match", "classify": "Place", "dedupe": "Repeat?",
              "watchlist": "Watch", "rules": "Rule", "disposition": "Result"}

RULE_TEXT = {
    "N1": "Structured row: no model needed",
    "N2": "Free-text post: a model extracted the fields and every value was found verbatim in the text",
    "I1": f"Identity score met the confirm threshold ({config.CONFIRM_THRESHOLD})",
    "C1": "Destination checked against the customer, prospect and competitor lists",
    "D1": "First time this person and destination were seen",
    "W1": "Contact is a champion or executive sponsor",
    "X1": "Final label recorded",
    **GUARDS, **{k: v[4] for k, v in RULES.items()},
}


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def build(feed: str, backend: str) -> str:
    res = ROOT / "results" / feed / backend
    dat = ROOT / "data" / feed
    decisions = load(res / "decisions.json")
    events = {e["event_id"]: e for e in load(dat / "events.json")}
    contacts = {c["id"]: c for c in load(dat / "contacts.json")}
    accounts = {a["id"]: a for a in load(dat / "accounts.json")}

    def by_event(name):
        out = {}
        for x in load(res / f"{name}.json"):
            out.setdefault(x["event_id"], x)
        return out

    flags, tasks = by_event("flags"), by_event("tasks")
    notes, supp, upd = by_event("notifications"), by_event("suppressions"), by_event("record_updates")
    queue = by_event("queue")

    out_events = []
    for d in sorted(decisions, key=lambda x: x["event_id"]):
        eid = d["event_id"]
        ev = events[eid]
        c = contacts.get(d.get("contact_id"))
        a = accounts.get(d.get("account_id"))
        q = queue.get(eid)
        item = {
            "id": eid, "date": ev["received_at"], "fmt": ev["format"],
            "raw": ev.get("text") or ev.get("structured"),
            "label": d["label"], "rule": d["rule"], "cls": CLASS[d["rule"]],
            "ruleText": RULE_TEXT.get(d["rule"], ""), "payload": d["payload"],
            "identity": {k: d["identity"].get(k) for k in ("status", "score", "evidence", "explanation")},
            "steps": [{**s, "ruleText": RULE_TEXT.get(s["rule"], "")} for s in d["steps"]],
            "contact": c and {"name": c["full_name"], "role": c["role"], "title": c["title"], "city": c["city"]},
            "account": a and {"name": a["name"], "plan": a["plan"], "arr": a["arr"], "renewal": a["renewal_date"],
                              "csm": a["csm"], "am": a["account_manager"], "usage": a["usage_level"]},
            "flag": flags.get(eid), "task": tasks.get(eid), "note": notes.get(eid),
            "supp": supp.get(eid), "upd": upd.get(eid), "queue": q,
        }
        out_events.append(item)

    acc = load(res / "acceptance.json")
    tests = []
    for t in acc["tests"]:
        tests.append({"n": t["n"], "name": t["name"], "cond": t["condition"], "now": t["short"],
                      "passed": t["passed"], "v1": RUN1[t["n"]], "v1pass": RUN1_PASS[t["n"]],
                      "measured": t["measured"]})
    counts = {}
    for e in out_events:
        counts[e["cls"]] = counts.get(e["cls"], 0) + 1
    data = {
        "feed": feed, "backend": backend, "events": out_events, "tests": tests,
        "passed": sum(t["passed"] for t in tests), "counts": counts,
        "flags": len(flags), "drafts": sum(1 for e in out_events if e["queue"] and e["queue"]["type"] == "outreach_draft"),
        "thresholds": {"confirm": config.CONFIRM_THRESHOLD, "review": config.REVIEW_THRESHOLD},
        "stats": load(res / "stats.json"),
    }
    tpl = (ROOT / "demo" / "walkthrough_template.html").read_text(encoding="utf-8")
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return tpl.replace("/*__DATA__*/null", blob)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", default="eval2")
    ap.add_argument("--backend", default="recorded")
    args = ap.parse_args()
    html = build(args.feed, args.backend)
    (ROOT / "docs" / "walkthrough.html").write_text(html, encoding="utf-8")
    print(f"wrote docs/walkthrough.html ({len(html) // 1024} KB)")


if __name__ == "__main__":
    main()
