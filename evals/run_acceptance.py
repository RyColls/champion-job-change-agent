"""Run the nine acceptance tests against the answer key and publish the results (passes AND failures).

    python -m evals.run_acceptance --feed eval --backend template

Reads: results/<feed>/<backend>/*.json (agent output), evals/keys/<feed>.json (answer key), data/<feed>/ (records).
Writes: results/<feed>/<backend>/acceptance.json and acceptance.md

Scoring definitions (fixed before the eval run, written down in DESIGN.md):
  * "caught" (test 1) = the agent auto-confirmed the person and classified a departure. Events held in
    identity review are reported separately and do NOT count as caught.
  * test 6 is strict: a real departure that was held in review or missed counts as a failure.
  * test 7 = (a) independent audit of every queued draft and history summary + (b) planted-fact tests.
"""
from __future__ import annotations

import argparse
import copy
import json
import random
from pathlib import Path

from agent.pipeline import STEPS
from agent.queue import ApprovalQueue, Outbox
from agent.verify import verify_draft
from evals.independent_audit import audit_text, build_lexicon, record_blob

ROOT = Path(__file__).resolve().parent.parent


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def why(dec: dict) -> str:
    """One-line explanation of what the agent did with an event, from its own audit trail."""
    ident = dec.get("identity") or {}
    if dec["label"] == "identity_review":
        sig = ", ".join(f"{e['signal']} {e['points']:+.1f}" for e in ident.get("evidence", []))
        return f"held in identity review: score {ident.get('score')} is below the confirm threshold ({sig})"
    if dec["label"] == "no_match":
        return f"treated as a different person: {ident.get('reason')}"
    if dec["label"] == "normalize_failed":
        return "free-text event could not be normalized"
    return f"labelled {dec['label']} by rule {dec['rule']}"


def run(feed: str, backend: str) -> dict:
    res = ROOT / "results" / feed / backend
    key = load(ROOT / "evals" / "keys" / f"{feed}.json")["events"]
    decisions = {d["event_id"]: d for d in load(res / "decisions.json")}
    queue = load(res / "queue.json")
    flags = {f["id"]: f for f in load(res / "flags.json")}
    run_info = load(res / "run.json")
    stats = load(res / "stats.json")
    data = ROOT / "data" / feed
    accounts = {a["id"]: a for a in load(data / "accounts.json")}
    contacts = {c["id"]: c for c in load(data / "contacts.json")}
    prospects = {p["id"]: p for p in load(data / "prospects.json")}
    out: dict = {"feed": feed, "backend": run_info["backend"], "tests": [], "extra": {}}

    def add(n, name, condition, measured, passed, failing=None, note=None):
        out["tests"].append({"n": n, "name": name, "condition": condition, "measured": measured,
                             "passed": passed, "failing_events": failing or [], "note": note})

    # ---- 1 detection
    real = [e for e, k in key.items() if k["real_departure"]]
    caught = [e for e in real if decisions[e]["label"].startswith("departure:")]
    missed = [e for e in real if e not in caught]
    add(1, "Detection", "At least 52 of the 55 real departures are caught",
        f"{len(caught)} of {len(real)} caught; {sum(decisions[e]['label'] == 'identity_review' for e in missed)} of the "
        f"{len(missed)} missed were held in identity review (not counted as caught)",
        len(caught) >= 52,
        [{"event_id": e, "type": key[e]["type"], "noise": key[e]["noise"], "why": why(decisions[e])} for e in missed])

    # ---- 2 name collisions
    coll = [e for e, k in key.items() if k["type"] == "collision"]
    trig = [e for e in coll if decisions[e]["plays"] or decisions[e]["label"].startswith(("departure:", "same_"))]
    by_label = {}
    for e in coll:
        by_label[decisions[e]["label"]] = by_label.get(decisions[e]["label"], 0) + 1
    add(2, "Name collisions", "0 of 9 trigger any play", f"{len(trig)} of {len(coll)} triggered a play; "
        f"outcomes {by_label}", not trig,
        [{"event_id": e, "level": key[e]["collision_level"], "why": why(decisions[e])} for e in trig])

    # ---- 3 duplicates
    dups = [e for e, k in key.items() if k["type"] == "duplicate"]
    bad = []
    for e in dups:
        group = [e, key[e]["dup_of"]]
        for kind in ("risk_flag", "csm_task", "queue_item"):
            if sum(1 for g in group if kind in decisions[g]["plays"]) > 1:
                bad.append({"event_id": e, "duplicate_of": key[e]["dup_of"], "play": kind,
                            "why": "a second task was created"})
    add(3, "Duplicates", "0 of 4 create a second task",
        f"{len({b['event_id'] for b in bad})} of {len(dups)} created a second task", not bad, bad)

    # ---- 4 classification
    mism = [e for e, k in key.items() if decisions[e]["label"] not in k["acceptable_labels"]]
    ok = len(key) - len(mism)
    add(4, "Classification", "At least 95% of events match the answer key",
        f"{ok} of {len(key)} match ({100 * ok / len(key):.1f}%)", ok / len(key) >= 0.95,
        [{"event_id": e, "type": key[e]["type"], "expected": key[e]["expected_label"],
          "got": decisions[e]["label"], "why": why(decisions[e])} for e in mism])

    # ---- 5 competitor suppression
    comp = [e for e, k in key.items() if k["type"] == "moved_competitor"]
    drafts_for_comp = [q for q in queue if q["event_id"] in comp and q["type"] in ("outreach_draft", "draft_blocked")]
    suppressed = sum(1 for e in comp if "suppression" in decisions[e]["plays"])
    add(5, "Competitor suppression", "0 outreach drafts for the 5 competitor moves",
        f"{len(drafts_for_comp)} drafts for {len(comp)} competitor moves; {suppressed} were explicitly suppressed "
        f"(the rest were held before reaching the rules)", not drafts_for_comp,
        [{"event_id": q["event_id"], "why": "a draft exists"} for q in drafts_for_comp])

    # ---- 6 old-account play
    wrong = []
    for e in real:
        d = decisions[e]
        fid = d["plays"].get("risk_flag")
        if not fid:
            wrong.append({"event_id": e, "why": "no risk flag: " + why(d)})
        elif flags[fid]["days_until_renewal"] != key[e]["days_until_renewal"]:
            wrong.append({"event_id": e, "why": f"days until renewal {flags[fid]['days_until_renewal']} "
                                                f"!= {key[e]['days_until_renewal']}"})
    add(6, "Old-account play", "Fires on every real departure, with the correct days until renewal",
        f"{len(real) - len(wrong)} of {len(real)} fired with the correct days until renewal",
        not wrong, wrong, "Strict: departures held in identity review count as failures here.")

    # ---- 7 draft integrity
    lex = build_lexicon(data)
    drafts = [q for q in queue if q["type"] == "outreach_draft"]
    findings = []
    for q in drafts:
        blob = record_blob(contacts[q["contact_id"]], accounts[contacts[q["contact_id"]]["account_id"]],
                           prospects[q["prospect_id"]], decisions[q["event_id"]]["payload"])
        for what, text in (("draft", f"{q['subject']}\n{q['body']}"), ("history summary", q["history_summary"])):
            for f in audit_text(text, blob, lex):
                findings.append({"queue_id": q["id"], "event_id": q["event_id"], "in": what, "finding": f})
    rng = random.Random(11)
    other_accounts = [a["name"] for a in accounts.values()]
    all_first = sorted({c["first_name"] for c in contacts.values()})
    cities = sorted({c["city"] for c in contacts.values()})
    planted = {"agent_verifier": 0, "independent_audit": 0, "total": 0}
    missed_plants = []
    for q in drafts[:12]:
        c = contacts[q["contact_id"]]
        acct = accounts[c["account_id"]]
        blob = record_blob(c, acct, prospects[q["prospect_id"]], decisions[q["event_id"]]["payload"])
        swap = rng.choice([n for n in other_accounts if n != acct["name"] and n.lower() not in blob])
        city = rng.choice([x for x in cities if x.lower() not in blob])
        first = rng.choice([x for x in all_first if x.lower() not in blob])
        plants = {
            "invented_outcome": q["body"] + "\n\nCairnboard helped your team cut onboarding time by 40%.",
            "wrong_company": q["body"].replace(acct["name"], swap),
            "invented_duration": q["body"] + "\n\nYou were with us for three years.",
            "wrong_city": q["body"] + f"\n\nHope {city} is treating you well.",
            "invented_person": q["body"] + f"\n\nSay hi to {first} from us.",
        }
        for kind, body in plants.items():
            planted["total"] += 1
            v = not verify_draft({"subject": q["subject"], "body": body, "claims": q["claims"]}, q["facts_used"])["ok"]
            a = bool(audit_text(f"{q['subject']}\n{body}", blob, lex))
            planted["agent_verifier"] += v
            planted["independent_audit"] += a
            if not (v and a):
                missed_plants.append({"queue_id": q["id"], "plant": kind, "agent_verifier_blocked": v,
                                      "independent_audit_flagged": a})
    t7_ok = not findings and planted["agent_verifier"] == planted["total"] and not missed_plants
    add(7, "Draft integrity", "0 facts in any draft that are not in the record",
        f"(a) independent audit of {len(drafts)} queued drafts and summaries: {len(findings)} unsupported facts; "
        f"(b) planted-fact tests: agent verifier blocked {planted['agent_verifier']} of {planted['total']}, "
        f"independent audit flagged {planted['independent_audit']} of {planted['total']}; "
        f"first-pass blocks {stats['drafts_blocked_first_pass']} of {stats['drafts']} drafts, "
        f"{stats['drafts_blocked_final']} blocked after retry",
        t7_ok, findings + missed_plants,
        "The verifier checks entities, numbers, quantities and outcome language. It cannot verify arbitrary "
        "lowercase prose claims; those are limited by the prompt and by human review.")

    # ---- 8 approval gate
    problems = []
    states = {q["status"] for q in queue}
    if states - {"pending", "needs_manual_draft"}:
        problems.append(f"pipeline left items in states {states}")
    aq = ApprovalQueue(copy.deepcopy(queue), Outbox())
    if aq.outbox.sent:
        problems.append("outbox was not empty before any human action")
    first_draft = next((i for i in aq.items.values() if i["type"] == "outreach_draft"), None)
    refused = 0
    if first_draft:
        try:
            aq.outbox.send(first_draft)
        except PermissionError:
            refused += 1
        try:
            aq.act(first_draft["id"], "approve", reviewer="")
        except PermissionError:
            refused += 1
        if refused != 2 or aq.outbox.sent:
            problems.append("outbox accepted an item without a human approval")
        aq.act(first_draft["id"], "approve", reviewer="rep.demo")
        if len(aq.outbox.sent) != 1 or aq.outbox.sent[0]["approved_by"] != "rep.demo":
            problems.append("an approved item did not reach the (mock) outbox exactly once")
    blocked = next((i for i in aq.items.values() if i["type"] == "draft_blocked"), None)
    if blocked:
        try:
            aq.act(blocked["id"], "approve", reviewer="rep.demo")
            problems.append("a blocked draft could be approved")
        except (PermissionError, ValueError):
            pass
    add(8, "Approval gate", "Nothing leaves the queue without a human action",
        f"{len([q for q in queue if q['type'] == 'outreach_draft'])} drafts left pending by the pipeline; outbox "
        f"empty until a named human acted; direct sends refused; unapproved sends refused: {refused} of 2",
        not problems, [{"why": p} for p in problems],
        "The outbox is a mock. Nothing real is ever sent.")

    # ---- 9 audit trail
    gaps = []
    for e, d in decisions.items():
        steps = [s["step"] for s in d.get("steps", [])]
        if steps != STEPS:
            gaps.append({"event_id": e, "why": f"steps are {steps}"})
            continue
        for s in d["steps"]:
            if not s.get("rule") or not s.get("detail"):
                gaps.append({"event_id": e, "why": f"step {s['step']} has no rule or detail"})
    add(9, "Audit trail", "Every one of the 80 events shows each decision and the rule behind it",
        f"{len(decisions) - len({g['event_id'] for g in gaps})} of {len(decisions)} events have all "
        f"{len(STEPS)} steps with a rule and detail", not gaps and len(decisions) == 80, gaps)

    # ---- extra measures (not pass/fail)
    out["extra"] = {
        "queue_counts": {t: sum(1 for q in queue if q["type"] == t) for t in sorted({q["type"] for q in queue})},
        "identity_review_events": [e for e, d in decisions.items() if d["label"] == "identity_review"],
        # what is actually sitting in the review queue: real moves and look-alike strangers, side by side
        "identity_review_composition": {
            t: sum(1 for e, d in decisions.items() if d["label"] == "identity_review" and key[e]["type"] == t)
            for t in sorted({key[e]["type"] for e, d in decisions.items() if d["label"] == "identity_review"})},
        "ai_calls": stats["ai_calls"],
        "draft_stats": {k: stats[k] for k in ("drafts", "drafts_blocked_first_pass", "drafts_blocked_final",
                                              "draft_retries", "summaries_failed_check")},
    }
    out["passed"] = sum(t["passed"] for t in out["tests"])
    (res / "acceptance.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (res / "acceptance.md").write_text(render_md(out), encoding="utf-8")
    return out


def render_md(o: dict) -> str:
    lines = [f"# Acceptance results: {o['feed']} feed", "",
             f"Backend for the AI steps: `{o['backend']}`. Measured against the answer key in this project on "
             f"simulated, fictional data. {o['passed']} of {len(o['tests'])} tests pass.", "",
             "| # | Test | Pass condition | Measured | Result |", "|---|---|---|---|---|"]
    for t in o["tests"]:
        lines.append(f"| {t['n']} | {t['name']} | {t['condition']} | {t['measured']} | "
                     f"{'PASS' if t['passed'] else '**FAIL**'} |")
    for t in o["tests"]:
        if t["failing_events"] or t["note"]:
            lines += ["", f"## Test {t['n']}: {t['name']}", ""]
            if t["note"]:
                lines += [f"_{t['note']}_", ""]
            for f in t["failing_events"]:
                lines.append("- " + ", ".join(f"{k}: {v}" for k, v in f.items()))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", choices=["dev", "eval", "eval2"], required=True)
    ap.add_argument("--backend", choices=["template", "recorded", "live"], default="template")
    a = ap.parse_args()
    r = run(a.feed, a.backend)
    for t in r["tests"]:
        print(f"{'PASS' if t['passed'] else 'FAIL'}  {t['n']}. {t['name']}: {t['measured']}")
    print(f"{r['passed']} of {len(r['tests'])} pass")
