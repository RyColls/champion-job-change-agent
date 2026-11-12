"""Identity resolution: is the person in this event the contact in our records?

This is CODE, not a model. It scores evidence in points and applies two thresholds. The model only
explains the result afterwards (see ai.py) and cannot change it.

  score >= CONFIRM_THRESHOLD            -> confirmed (I1)
  REVIEW_THRESHOLD <= score < CONFIRM   -> identity review, a human decides, no play fires (G3)
  score <  REVIEW_THRESHOLD             -> not the same person (G2)
"""
from __future__ import annotations

from . import config
from .company import CompanyIndex
from .textutil import norm_company, ratio, title_sim

NICKNAMES = {"kate": "katherine", "mike": "michael", "alex": "alexander", "liz": "elizabeth",
             "chris": "christopher", "jen": "jennifer", "matt": "matthew", "becca": "rebecca",
             "nick": "nicholas", "sam": "samantha", "ben": "benjamin", "jon": "jonathan"}


def canon_first(first: str) -> str:
    f = first.lower().strip()
    return NICKNAMES.get(f, f)


def split_name(full: str) -> tuple[str, str]:
    parts = full.strip().split()
    return (parts[0], parts[-1]) if len(parts) > 1 else (parts[0], "")


class IdentityResolver:
    def __init__(self, contacts: list[dict], accounts: list[dict], index: CompanyIndex):
        self.contacts = contacts
        self.accounts = {a["id"]: a for a in accounts}
        self.index = index
        self.by_last: dict[str, list[dict]] = {}
        self.by_account: dict[str, list[dict]] = {}
        self.by_domain = {a["domain"]: a["id"] for a in accounts}
        for c in contacts:
            self.by_last.setdefault(c["last_name"].lower(), []).append(c)
            self.by_account.setdefault(c["account_id"], []).append(c)

    # ------------------------------------------------------------------ candidates
    def candidates(self, p: dict) -> list[dict]:
        first, last = split_name(p["full_name"])
        cf = canon_first(first)
        found: dict[str, dict] = {}
        for c in self.by_last.get(last.lower(), []):
            if canon_first(c["first_name"]) == cf:
                found[c["id"]] = c
        # a changed surname: look inside the account the person says they came from
        acct_ids = set()
        ent = self.index.resolve(p.get("prior_employer"))
        if ent and ent["kind"] == "customer":
            acct_ids.add(ent["id"])
        if p.get("prior_email_domain") in self.by_domain:
            acct_ids.add(self.by_domain[p["prior_email_domain"]])
        for aid in acct_ids:
            for c in self.by_account.get(aid, []):
                if canon_first(c["first_name"]) == cf:
                    found[c["id"]] = c
        return list(found.values())

    # ------------------------------------------------------------------ scoring
    def score(self, c: dict, p: dict) -> tuple[float, list[dict]]:
        acct = self.accounts[c["account_id"]]
        ev: list[dict] = []

        def add(signal: str, pts: float, detail: str) -> None:
            ev.append({"signal": signal, "points": pts, "detail": detail})

        first, last = split_name(p["full_name"])
        if p["full_name"].lower() == c["full_name"].lower():
            add("name", 3.0, "full name matches exactly")
        elif canon_first(first) == canon_first(c["first_name"]) and last.lower() == c["last_name"].lower():
            add("name", 2.5, f"first name is a known variant ({first} / {c['first_name']}), surname matches")
        else:
            add("name", 1.0, f"first name matches but surname differs ({last} / {c['last_name']})")

        prior = p.get("prior_employer")
        if prior:
            ent = self.index.resolve(prior)
            if ent and ent["id"] == acct["id"]:
                add("employer", 3.0, f"prior employer '{prior}' is {acct['name']}")
            elif ratio(norm_company(prior), norm_company(acct["name"])) >= 0.8:
                add("employer", 1.5, f"prior employer '{prior}' is close to {acct['name']}")
            else:
                add("employer", -3.0, f"prior employer '{prior}' is not {acct['name']}")
        else:
            ent = self.index.resolve(p.get("new_employer"))
            if ent and ent["id"] == acct["id"]:
                add("employer", 3.0, f"still at {acct['name']} (new title there)")
            else:
                add("employer", 0.0, "no prior employer given")

        dom = p.get("prior_email_domain")
        if dom:
            if dom == acct["domain"]:
                add("email_domain", 3.0, f"prior e-mail domain {dom} matches the account")
            else:
                add("email_domain", -4.0, f"prior e-mail domain {dom} does not match {acct['domain']}")

        loc = p.get("location")
        if loc:
            if loc.lower() == c["city"].lower():
                add("city", 1.0, f"location {loc} matches")
            else:
                # people relocate when they change jobs, so a different city is not evidence against a match
                add("city", 0.0, f"location {loc} differs from {c['city']} (no penalty: people relocate)")

        if p.get("prior_title"):
            if title_sim(p["prior_title"], c["title"]) >= 0.5:
                add("title", 1.0, f"prior title '{p['prior_title']}' is similar to '{c['title']}'")
            else:
                add("title", -0.5, f"prior title '{p['prior_title']}' differs from '{c['title']}'")
        return round(sum(e["points"] for e in ev), 2), ev

    # ------------------------------------------------------------------ decision
    def resolve(self, p: dict) -> dict:
        cands = self.candidates(p)
        scored = sorted(((self.score(c, p), c) for c in cands), key=lambda t: -t[0][0])
        if not scored:
            return {"status": "no_match", "rule": "G2", "score": None, "contact_id": None, "evidence": [],
                    "reason": "no contact in the records shares this name", "candidates": []}
        (best, ev), c = scored[0]
        summary = [{"contact_id": cc["id"], "score": s} for (s, _), cc in scored[:3]]
        base = {"contact_id": c["id"], "score": best, "evidence": ev, "candidates": summary}
        if best < config.REVIEW_THRESHOLD:
            return {**base, "status": "no_match", "rule": "G2",
                    "reason": f"score {best} is below the review threshold {config.REVIEW_THRESHOLD}"}
        if len(scored) > 1 and scored[1][0][0] >= config.REVIEW_THRESHOLD \
                and best - scored[1][0][0] < config.AMBIGUITY_MARGIN:
            return {**base, "status": "review", "rule": "G3",
                    "reason": "two candidates score within the ambiguity margin"}
        if best < config.CONFIRM_THRESHOLD:
            return {**base, "status": "review", "rule": "G3",
                    "reason": f"score {best} is between review {config.REVIEW_THRESHOLD} and "
                              f"confirm {config.CONFIRM_THRESHOLD}"}
        return {**base, "status": "confirmed", "rule": "I1",
                "reason": f"score {best} meets the confirm threshold {config.CONFIRM_THRESHOLD}"}
