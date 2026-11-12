"""Independent draft auditor for acceptance test 7.

Deliberately shares NO code with agent/verify.py and uses a different method:

  agent verifier   : claims must match a curated fact sheet; scans for numbers, mid-sentence capitals, outcome words
  this auditor     : builds a lexicon of every company, person name and city in the whole dataset, then flags
                     any lexicon entity that appears in the text but NOT in this record's own data, plus any
                     number, duration/quantity word or outcome phrase.

So a draft that names the wrong company, person or city is caught by an entity lookup, not by guessing
which words look like proper nouns.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

OUTCOME = re.compile(r"(%|\$|\b(saved?|saving|increase\w*|decrease\w*|revenue|roi|churn\w*|pipeline|guarantee\w*|"
                     r"doubl\w*|boost\w*|grew|growth|reduc\w+|improv\w+|faster|cut)\b)", re.I)
PRONOUN = re.compile(r"\b(he|she|him|her|hers|his|himself|herself)\b", re.I)
QUANTITY = re.compile(r"\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|"
                      r"hundred|thousand|million|dozen|years?|months?|weeks?|quarters?)\b", re.I)


def build_lexicon(data_dir: Path) -> re.Pattern:
    terms: set[str] = set()
    for fname in ("accounts", "prospects", "competitors"):
        for row in json.loads((data_dir / f"{fname}.json").read_text()):
            terms.add(row["name"].lower())
            terms.add(" ".join(row["parts"]).lower())
    for c in json.loads((data_dir / "contacts.json").read_text()):
        terms.update([c["first_name"].lower(), c["last_name"].lower(), c["city"].lower()])
    terms.discard("")
    alt = "|".join(sorted((re.escape(t) for t in terms), key=len, reverse=True))
    return re.compile(rf"\b({alt})\b", re.I)


def record_blob(*records: dict | None) -> str:
    return json.dumps([r for r in records if r], ensure_ascii=False).lower()


def audit_text(text: str, blob: str, lexicon: re.Pattern, allow_phrases: tuple[str, ...] = ()) -> list[str]:
    cleaned = text
    for ph in allow_phrases:
        cleaned = re.sub(re.escape(ph), " ", cleaned, flags=re.I)
    findings: list[str] = []
    seen: set[str] = set()
    for m in lexicon.finditer(cleaned):
        t = m.group(1).lower()
        if t not in seen and t not in blob:
            seen.add(t)
            findings.append(f"entity '{m.group(1)}' is not in this record")
    for num in re.findall(r"\d+", cleaned):
        if num not in blob:
            findings.append(f"number '{num}' is not in this record")
    for m in OUTCOME.finditer(cleaned):
        findings.append(f"outcome language '{m.group(0)}'")
    for m in PRONOUN.finditer(cleaned):
        findings.append(f"gendered pronoun '{m.group(0)}' (the record has no gender)")
    for m in QUANTITY.finditer(cleaned):
        findings.append(f"unsupported quantity or duration '{m.group(0)}'")
    return findings
