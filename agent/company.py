"""Resolve an employer string to a known customer, prospect or competitor."""
from __future__ import annotations

from .textutil import norm_company, ratio

FUZZY = 0.9


class CompanyIndex:
    def __init__(self, accounts: list[dict], prospects: list[dict], competitors: list[dict]):
        self.entries: list[dict] = []
        for a in accounts:
            self.entries.append({"kind": "customer", "id": a["id"], "name": a["name"], "icp_fit": None,
                                 "norm": norm_company(a["name"])})
        for p in prospects:
            self.entries.append({"kind": "prospect", "id": p["id"], "name": p["name"], "icp_fit": p["icp_fit"],
                                 "norm": norm_company(p["name"])})
        for c in competitors:
            self.entries.append({"kind": "competitor", "id": c["id"], "name": c["name"], "icp_fit": None,
                                 "norm": norm_company(c["name"])})
        self.by_norm = {e["norm"]: e for e in self.entries}

    def resolve(self, name: str | None) -> dict | None:
        n = norm_company(name)
        if not n:
            return None
        if n in self.by_norm:
            return self.by_norm[n]
        close = [e for e in self.entries if ratio(n, e["norm"]) >= FUZZY]
        return close[0] if len(close) == 1 else None
