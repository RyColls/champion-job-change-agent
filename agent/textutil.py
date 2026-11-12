"""Small, dependency-free text helpers."""
from __future__ import annotations

import difflib
import re

COMPANY_NOISE = {"inc", "llc", "ltd", "co", "corp", "the", "incorporated", "company"}
TITLE_ABBR = {"sr": "senior", "jr": "junior", "mgr": "manager", "pm": "product manager",
              "ops": "operations", "vp": "vp"}


def norm_company(name: str | None) -> str:
    """'The Lumen Forge, Inc.' -> 'lumenforge'."""
    if not name:
        return ""
    s = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    return "".join(t for t in s.split() if t not in COMPANY_NOISE)


def title_tokens(title: str | None) -> set[str]:
    if not title:
        return set()
    s = re.sub(r"[^a-z0-9 ]", " ", title.lower())
    out: list[str] = []
    for t in s.split():
        out += TITLE_ABBR.get(t, t).split()
    return set(out)


def title_sim(a: str | None, b: str | None) -> float:
    ta, tb = title_tokens(a), title_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def squash(s: str) -> str:
    """Lowercase and collapse whitespace; used for 'does this value appear in that text' checks."""
    return re.sub(r"\s+", " ", s.lower()).strip()
