"""Draft integrity: code checks every fact in an AI-written draft against the record.

The model must return its draft together with `claims`, each pointing at a field of the fact sheet.
This module then checks, with no model involved:

  1. every claim's field exists in the fact sheet and the claim text equals that field's value
  2. every claim text actually appears in the subject/body
  3. every number in the text appears in the fact sheet
  4. every capitalized word that is not sentence-initial is a known fact word or an allowed word
  5. no outcome language (savings, percentages, revenue, churn, pipeline, guarantees)

A draft that fails any check is blocked. It never reaches a rep as an approvable draft.
"""
from __future__ import annotations

import re

from . import config
from .textutil import squash

ALLOWED_WORDS = {"cairnboard", "sales", "assist", "team", "the", "i", "i'm", "i'd", "we", "we'd", "we'll"}
FORBIDDEN = re.compile(
    r"(%|\$|\bsav(e|ed|es|ing|ings)\b|\bincreas\w*\b|\brevenue\b|\broi\b|\bchurn\w*\b|\bpipeline\b|"
    r"\bguarantee\w*\b|\bdoubl\w*\b|\bboost\w*\b|\bgrew\b|\bgrowth\b|"
    # spelled-out quantities and durations ("three years") are unsupported facts too
    r"\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|hundred|"
    r"thousand|million|dozen|years?|months?|weeks?|quarters?)\b|"
    # the record has no gender, so a pronoun would be an inference about the person
    r"\b(he|she|him|her|hers|his|himself|herself)\b)", re.I)
WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")


def build_fact_sheet(contact: dict, account: dict, payload: dict, new_entity: dict | None) -> dict[str, str]:
    """Everything a draft or summary is allowed to say. Only record fields; nothing inferred."""
    facts = {
        "contact.first_name": payload["full_name"].split()[0],
        "contact.full_name": contact["full_name"],
        "contact.role_label": config.ROLE_LABEL[contact["role"]],
        "contact.old_title": contact["title"],
        "contact.signup_date": contact["signup_date"],
        "contact.last_active_date": contact["last_active_date"],
        "contact.boards_created": str(contact["boards_created"]),
        "account.name": account["name"],
        "account.plan": account["plan"],
        "account.usage_level": account["usage_level"],
        "account.customer_since": account["customer_since"],
    }
    if new_entity:
        facts["new_company.name"] = new_entity["name"]
    if payload.get("new_title"):
        facts["new_title"] = payload["new_title"]
    return facts


def _vocab(facts: dict[str, str]) -> set[str]:
    words: set[str] = set()
    for v in facts.values():
        words |= {w.lower() for w in WORD.findall(v)}
    return words


def _numbers(s: str) -> set[str]:
    return set(re.findall(r"\d+", s))


def _sentence_initial(text: str, start: int) -> bool:
    i = start - 1
    while i >= 0 and text[i] in " \t":
        i -= 1
    return i < 0 or text[i] in ".!?\n"


def verify_text(text: str, facts: dict[str, str], claims: list[dict] | None = None) -> dict:
    problems: list[str] = []
    low = squash(text)
    fact_nums = set().union(*[_numbers(v) for v in facts.values()]) if facts else set()
    vocab = _vocab(facts) | ALLOWED_WORDS

    for cl in claims or []:
        field, ctext = cl.get("field"), cl.get("text", "")
        if field not in facts:
            problems.append(f"claim '{ctext}' points at unknown field '{field}'")
        elif squash(ctext) != squash(facts[field]):
            problems.append(f"claim '{ctext}' does not equal record value for {field} ('{facts[field]}')")
        if squash(ctext) not in low:
            problems.append(f"claim '{ctext}' does not appear in the text")
    for n in sorted(_numbers(text) - fact_nums):
        problems.append(f"number '{n}' is not in the record")
    for m in WORD.finditer(text):
        w = m.group(0)
        base = re.sub(r"['\u2019]s$", "", w).lower()  # "Camila's" is the record word "Camila"
        if w[0].isupper() and not _sentence_initial(text, m.start()) and base not in vocab:
            problems.append(f"'{w}' is not in the record")
    for m in FORBIDDEN.finditer(text):
        problems.append(f"outcome language not allowed: '{m.group(0)}'")
    return {"ok": not problems, "problems": problems}


def verify_draft(draft: dict, facts: dict[str, str]) -> dict:
    text = f"{draft.get('subject', '')}\n{draft.get('body', '')}"
    return verify_text(text, facts, draft.get("claims"))
