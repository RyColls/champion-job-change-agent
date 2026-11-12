"""The pipeline: event in, decisions, plays and an audit trail out.

  normalize -> identity -> classify -> dedupe -> watchlist -> rules -> disposition

Every event produces an entry for every step. A step that was not reached is logged as `skipped`
with the rule that stopped the event, so the audit log answers "why did nothing happen?" too.

This module must never read anything under evals/ (the answer key). tests/test_isolation.py checks it.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import config, plays, rules
from .ai import TemplateBackend
from .company import CompanyIndex
from .identity import IdentityResolver
from .textutil import norm_company, squash
from .verify import build_fact_sheet, verify_draft, verify_text

STEPS = ["normalize", "identity", "classify", "dedupe", "watchlist", "rules", "disposition"]
NORMAL_FIELDS = ["full_name", "prior_employer", "prior_title", "prior_email_domain", "new_employer", "new_title",
                 "location"]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class Pipeline:
    def __init__(self, data_dir: Path, backend):
        self.backend = backend
        d = Path(data_dir)
        self.accounts = {a["id"]: a for a in load_json(d / "accounts.json")}
        contacts = load_json(d / "contacts.json")
        self.contacts = {c["id"]: c for c in contacts}
        self.prospects = {p["id"]: p for p in load_json(d / "prospects.json")}
        self.competitors = {c["id"]: c for c in load_json(d / "competitors.json")}
        self.events = load_json(d / "events.json")
        self.by_account: dict[str, list[dict]] = {}
        for c in contacts:
            self.by_account.setdefault(c["account_id"], []).append(c)
        self.index = CompanyIndex(list(self.accounts.values()), list(self.prospects.values()),
                                  list(self.competitors.values()))
        self.resolver = IdentityResolver(contacts, list(self.accounts.values()), self.index)
        self.seen: dict[str, dt.date] = {}
        self.risk_keys: set[tuple] = set()
        self.out = {k: [] for k in ["decisions", "flags", "tasks", "queue", "notifications", "record_updates",
                                    "new_contacts", "suppressions"]}
        self.stats = {"ai_calls": {}, "drafts": 0, "drafts_blocked_first_pass": 0, "drafts_blocked_final": 0,
                      "summaries_failed_check": 0, "draft_retries": 0}
        self.n = {"flag": 0, "task": 0, "queue": 0, "newk": 0}

    # ------------------------------------------------------------------ helpers
    def ai(self, task: str, inp: dict) -> tuple[dict, dict]:
        out, prov = self.backend.call(task, inp)
        key = f"{task}|{prov['backend']}|{prov['model']}"
        self.stats["ai_calls"][key] = self.stats["ai_calls"].get(key, 0) + 1
        return out, prov

    def next_id(self, kind: str, prefix: str) -> str:
        self.n[kind] += 1
        return f"{prefix}{self.n[kind]:03d}"

    # ------------------------------------------------------------------ normalize
    def normalize(self, ev: dict) -> tuple[dict | None, dict]:
        if ev["format"] == "structured":
            p = {k: ev["structured"].get(k) for k in NORMAL_FIELDS}
            return p, {"rule": "N1", "outcome": "ok", "detail": "structured event, no AI needed"}
        out, prov = self.ai("normalize", {"text": ev["text"]})
        p = {k: (out.get(k) or None) for k in NORMAL_FIELDS}
        text = squash(ev["text"])
        bad = [k for k, v in p.items() if v and squash(str(v)) not in text]
        if not p["full_name"] or bad:
            why = "no name extracted" if not p["full_name"] else f"values not found in the text: {bad}"
            return None, {"rule": "G5", "outcome": "failed", "detail": f"{why} ({prov['backend']})"}
        return p, {"rule": "N2", "outcome": "ok",
                   "detail": f"extracted by {prov['model'] or prov['backend']}; every value found verbatim in the text"}

    # ------------------------------------------------------------------ classify
    def classify(self, p: dict, account: dict) -> tuple[str, dict | None]:
        if not p.get("new_employer"):
            return "none", None
        ent = self.index.resolve(p["new_employer"])
        if ent is None:
            return "unknown", None
        if ent["kind"] == "customer":
            return ("same_company" if ent["id"] == account["id"] else "customer"), ent
        if ent["kind"] == "competitor":
            return "competitor", ent
        return ("fit_prospect" if ent["icp_fit"] else "nofit_prospect"), ent

    # ------------------------------------------------------------------ main loop
    def run(self) -> dict:
        for ev in sorted(self.events, key=lambda e: (e["received_at"], e["event_id"])):
            self.process(ev)
        return {**self.out, "stats": self.stats}

    def process(self, ev: dict) -> None:
        log: dict[str, dict] = {}
        received = dt.date.fromisoformat(ev["received_at"])
        dec = {"event_id": ev["event_id"], "received_at": ev["received_at"], "label": None, "rule": None,
               "contact_id": None, "account_id": None, "identity": None, "destination": None,
               "new_company_play": "none", "old_account_play": "none", "plays": {}}

        def step(name: str, rule: str, outcome: str, detail: str) -> None:
            log[name] = {"step": name, "rule": rule, "outcome": outcome, "detail": detail}

        def finish(label: str, rule: str, stop: str | None = None) -> None:
            for s in STEPS[:-1]:
                if s not in log:
                    step(s, rule, "skipped", f"not reached: stopped at {stop} by {rule}")
            step("disposition", "X1", "ok", f"label={label} (decided by {rule})")
            dec["label"], dec["rule"] = label, rule
            dec["steps"] = [log[s] for s in STEPS]
            self.out["decisions"].append(dec)

        # 1. normalize
        p, info = self.normalize(ev)
        step("normalize", info["rule"], info["outcome"], info["detail"])
        if p is None:
            self.queue_item({"type": "identity_review", "event_id": ev["event_id"], "status": "pending",
                             "assigned_to": "revops", "reason": "event text could not be normalized and validated",
                             "text": ev.get("text")})
            return finish("normalize_failed", "G5", "normalize")
        dec["payload"] = p

        # 2. identity (code decides, model explains)
        ident = self.resolver.resolve(p)
        explanation = None
        if ident["contact_id"]:
            c0 = self.contacts[ident["contact_id"]]
            explanation, _ = self.ai("explain_identity", {
                "event_name": p["full_name"], "record_name": c0["full_name"], "evidence": ident["evidence"],
                "score": ident["score"], "decision": f"{ident['status']}: {ident['reason']}"})
            explanation = explanation.get("explanation")
        dec["identity"] = {k: ident[k] for k in ("status", "score", "reason", "candidates")}
        dec["identity"]["evidence"] = ident["evidence"]
        dec["identity"]["explanation"] = explanation
        step("identity", ident["rule"], ident["status"], ident["reason"] + (f". {explanation}" if explanation else ""))
        if ident["status"] == "no_match":
            return finish("no_match", "G2", "identity")
        if ident["status"] == "review":
            self.queue_item({"type": "identity_review", "event_id": ev["event_id"], "status": "pending",
                             "assigned_to": "revops", "contact_id": ident["contact_id"], "score": ident["score"],
                             "explanation": explanation, "evidence": ident["evidence"], "payload": p})
            dec["contact_id"] = ident["contact_id"]
            return finish("identity_review", "G3", "identity")
        contact = self.contacts[ident["contact_id"]]
        account = self.accounts[contact["account_id"]]
        dec["contact_id"], dec["account_id"] = contact["id"], account["id"]

        # 3. classify destination
        kind, ent = self.classify(p, account)
        dec["destination"] = kind
        step("classify", "C1", "ok", f"destination={kind}" + (f" ({ent['name']})" if ent else ""))

        # 4. dedupe
        if kind == "same_company":
            dkey = f"{contact['id']}|same|{norm_company(p.get('new_title'))}"
        elif kind == "none":
            dkey = f"{contact['id']}|none"
        else:
            dkey = f"{contact['id']}|{ent['id'] if ent else 'unk:' + norm_company(p['new_employer'])}"
        first = self.seen.get(dkey)
        if first is not None and (received - first).days <= config.DEDUPE_WINDOW_DAYS:
            step("dedupe", "G1", "duplicate",
                 f"same person and destination already handled {(received - first).days} days earlier")
            return finish("duplicate", "G1", "dedupe")
        self.seen[dkey] = received
        step("dedupe", "D1", "ok", "first time this person and destination were seen")

        # 5. watch list
        if contact["role"] not in config.WATCH_ROLES:
            step("watchlist", "G4", "not_watched", f"{contact['role']} is not on the watch list")
            return finish("unwatched_move", "G4", "watchlist")
        step("watchlist", "W1", "ok", f"{contact['role']} is on the watch list")

        # 6. rules and plays
        decision = rules.decide(kind)
        dec["new_company_play"], dec["old_account_play"] = decision["new_company_play"], decision["old_account_play"]
        step("rules", decision["rule"], "ok", decision["description"])
        if decision["old_account_play"] != "none":
            self.old_account_play(ev, dec, contact, account)
        self.new_company_play(ev, dec, decision, contact, account, p, ent)
        return finish(decision["label"], decision["rule"])

    # ------------------------------------------------------------------ plays
    def queue_item(self, item: dict) -> str:
        item["id"] = self.next_id("queue", "Q")
        self.out["queue"].append(item)
        return item["id"]

    def old_account_play(self, ev: dict, dec: dict, contact: dict, account: dict) -> None:
        key = (account["id"], contact["id"])
        if key in self.risk_keys:  # belt and braces: never a second task for the same departure
            return
        self.risk_keys.add(key)
        flag = plays.build_risk_flag(self.next_id("flag", "F"), ev, contact, account, self.by_account[account["id"]])
        task = plays.build_csm_task(self.next_id("task", "T"), flag, account, ev["received_at"])
        self.out["flags"].append(flag)
        self.out["tasks"].append(task)
        dec["plays"]["risk_flag"], dec["plays"]["csm_task"] = flag["id"], task["id"]

    def new_company_play(self, ev, dec, decision, contact, account, p, ent) -> None:
        play = decision["new_company_play"]
        if play == "create_contact_and_draft_outreach":
            self.outreach(ev, dec, decision, contact, account, p, ent)
        elif play == "notify_account_manager":
            target = self.accounts[ent["id"]]
            n = {"id": f"N{len(self.out['notifications']) + 1:03d}", "type": "account_manager_note",
                 "event_id": ev["event_id"], "to": target["account_manager"], "account_id": target["id"],
                 "message": f"{contact['full_name']}, a former champion at {account['name']}, has joined "
                            f"{target['name']}, an existing customer. Consider reaching out about expansion."}
            self.out["notifications"].append(n)
            dec["plays"]["notification"] = n["id"]
        elif play == "update_record":
            u = {"id": f"U{len(self.out['record_updates']) + 1:03d}", "event_id": ev["event_id"],
                 "contact_id": contact["id"], "field": "title", "old": contact["title"], "new": p.get("new_title")}
            self.out["record_updates"].append(u)
            dec["plays"]["record_update"] = u["id"]
        elif play == "suppress_outreach":
            s = {"id": f"S{len(self.out['suppressions']) + 1:03d}", "event_id": ev["event_id"],
                 "reason": "competitor", "competitor": ent["name"], "contact_id": contact["id"]}
            self.out["suppressions"].append(s)
            dec["plays"]["suppression"] = s["id"]
        elif play == "log_only_flag_for_revops_review":
            dec["plays"]["revops_review"] = self.queue_item({
                "type": "revops_review", "event_id": ev["event_id"], "status": "pending", "assigned_to": "revops",
                "reason": f"'{p['new_employer']}' is not in the customer, prospect or competitor lists",
                "contact_id": contact["id"]})

    def outreach(self, ev, dec, decision, contact, account, p, ent) -> None:
        prospect = self.prospects[ent["id"]]
        facts = build_fact_sheet(contact, account, p, ent)
        summary, _ = self.ai("history_summary", {"facts": facts})
        summary = summary.get("summary", "")
        if not verify_text(summary, facts)["ok"]:
            self.stats["summaries_failed_check"] += 1
            summary, _ = TemplateBackend().call("history_summary", {"facts": facts})
            summary = summary["summary"]
        nk = {"id": self.next_id("newk", "NK"), "from_contact_id": contact["id"], "name": contact["full_name"],
              "company_id": prospect["id"], "company": prospect["name"], "title": p.get("new_title"),
              "carried_history": {k: v for k, v in facts.items() if k.startswith(("contact.", "account."))}}
        self.out["new_contacts"].append(nk)
        dec["plays"]["new_contact"] = nk["id"]

        self.stats["drafts"] += 1
        draft, prov = self.ai("draft_outreach", {"facts": facts})
        check = verify_draft(draft, facts)
        first_pass_ok = check["ok"]
        if not check["ok"]:
            self.stats["drafts_blocked_first_pass"] += 1
            if self.backend.name != "template":  # a retry only makes sense for a model
                self.stats["draft_retries"] += 1
                draft, prov = self.ai("draft_outreach", {"facts": facts, "previous_problems": check["problems"]})
                check = verify_draft(draft, facts)
        base = {"event_id": ev["event_id"], "contact_id": contact["id"], "prospect_id": prospect["id"],
                "company": prospect["name"], "contact_name": contact["full_name"], "new_title": p.get("new_title"),
                "to": "e-mail to be found by the rep", "history_summary": summary, "rule": decision["rule"],
                "assigned_to": "sales-assist", "provenance": prov, "first_pass_ok": first_pass_ok,
                "verification": check, "facts_used": facts}
        if check["ok"]:
            qid = self.queue_item({**base, "type": "outreach_draft", "status": "pending",
                                   "subject": draft["subject"], "body": draft["body"], "claims": draft["claims"]})
        else:
            self.stats["drafts_blocked_final"] += 1
            qid = self.queue_item({**base, "type": "draft_blocked", "status": "needs_manual_draft",
                                   "blocked_problems": check["problems"]})
        dec["plays"]["queue_item"] = qid
