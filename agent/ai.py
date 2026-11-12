"""The AI steps and their backends.

Four tasks go through `Backend.call(task, inp)`:

  normalize          Haiku   free-text announcement -> fields
  explain_identity   Sonnet  explain the code-computed identity decision
  history_summary    Sonnet  summarize the person's history with Cairnboard
  draft_outreach     Sonnet  draft the outreach message (returns claims for the code verifier)

Three interchangeable backends:

  TemplateBackend   deterministic, no network. Used by tests and CI. It is a stand-in for the models; it
                    parses only the announcement templates the simulator produces.
  RecordedBackend   replays recorded model outputs keyed by a hash of (task, input). Falls back to the
                    template backend for anything not recorded and labels that in the provenance.
  LiveBackend       calls the Anthropic API with the models in config.TASK_MODEL (needs ANTHROPIC_API_KEY),
                    and appends every answer to the recording file so runs can be replayed.

Every output carries provenance: {"backend", "model"}.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from . import config, prompts

ROOT = Path(__file__).resolve().parent.parent
RECORDINGS = ROOT / "recordings" / "ai_recordings.json"


def task_key(task: str, inp: dict) -> str:
    blob = json.dumps({"task": task, "input": inp}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:20]


# ---------------------------------------------------------------------------- template backend
_T1 = re.compile(r"^(?P<full_name>.+?) has joined (?P<new_employer>.+?) as (?P<new_title>[^.]+?)\."
                 r"(?: Previously (?P<prior_title>[^.]+?)(?: at (?P<prior_employer>[^.]+?))?\.)?"
                 r"(?: Based in (?P<location>[^.]+?)\.)?$")
_T2 = re.compile(r"^Thrilled to share I'm starting a new chapter as (?P<new_title>.+?) at (?P<new_employer>.+?)!"
                 r"(?: After a great run at (?P<prior_employer>.+?), onward\.)? — (?P<full_name>[^,]+?)"
                 r"(?:, (?P<location>.+))?$")
_T3 = re.compile(r"^(?P<full_name>.+?) has left (?P<prior_employer>[^,.]+?)(?:, where they were (?P<prior_title>[^.]+?))?"
                 r"\. No new role announced\.$")
_T4 = re.compile(r"^Congratulations to (?P<full_name>.+?), now (?P<new_title>.+?) at (?P<new_employer>.+?)"
                 r"(?: \(formerly (?P<prior_title>.+?)\))?\.$")
FIELDS = ["full_name", "prior_employer", "prior_title", "new_employer", "new_title", "location"]


class TemplateBackend:
    name = "template"

    def call(self, task: str, inp: dict) -> tuple[dict, dict]:
        out = getattr(self, f"_{task}")(inp)
        return out, {"backend": "template", "model": None}

    def _normalize(self, inp: dict) -> dict:
        text = inp["text"]
        for rx in (_T1, _T2, _T3, _T4):
            m = rx.match(text)
            if m:
                d = m.groupdict()
                return {f: d.get(f) for f in FIELDS}
        return {f: None for f in FIELDS}

    def _explain_identity(self, inp: dict) -> dict:
        parts = [f"{e['detail']} ({e['points']:+.1f})" for e in inp["evidence"]]
        return {"explanation": f"Evidence: {'; '.join(parts)}. Total {inp['score']}. Decision: {inp['decision']}."}

    def _history_summary(self, inp: dict) -> dict:
        f = inp["facts"]
        return {"summary": (f"{f['contact.full_name']} was a {f['contact.role_label']} at {f['account.name']} "
                            f"({f['account.plan']} plan, {f['account.usage_level']} usage, customer since "
                            f"{f['account.customer_since']}). Signed up {f['contact.signup_date']}, created "
                            f"{f['contact.boards_created']} feedback boards, last active "
                            f"{f['contact.last_active_date']}.")}

    def _draft_outreach(self, inp: dict) -> dict:
        f = inp["facts"]
        first, old, new = f["contact.first_name"], f["account.name"], f["new_company.name"]
        role = f["contact.role_label"]
        article = "an" if role[0] in "aeiou" else "a"
        title = f.get("new_title")
        joined = f"joining {new} as {title}" if title else f"joining {new}"
        subject = f"Congratulations on the new role at {new}"
        body = (f"Hi {first},\n\nCongratulations on {joined}. As {article} {role} of Cairnboard at {old}, "
                f"you helped shape how your team handled product feedback, and we would love to hear how things "
                f"are going in the new seat.\n\nIf product feedback and roadmap tooling comes up at {new}, "
                f"I am happy to share what worked for your team at {old}. No pressure either way.\n\n"
                f"The Cairnboard sales-assist team")
        claims = [{"text": first, "field": "contact.first_name"}, {"text": new, "field": "new_company.name"},
                  {"text": old, "field": "account.name"}, {"text": role, "field": "contact.role_label"}]
        if title:
            claims.append({"text": title, "field": "new_title"})
        return {"subject": subject, "body": body, "claims": claims}


# ---------------------------------------------------------------------------- recorded backend
class RecordedBackend:
    name = "recorded"

    def __init__(self, path: Path = RECORDINGS):
        data = json.loads(path.read_text()) if path.exists() else {}
        self.rec = data.get("recordings", {})
        self.meta = data.get("meta", {})
        self.fallback = TemplateBackend()
        self.misses = 0

    def call(self, task: str, inp: dict) -> tuple[dict, dict]:
        r = self.rec.get(task_key(task, inp))
        if r and r["task"] == task:
            return r["output"], {"backend": "recorded", "model": r["model"]}
        self.misses += 1
        out, _ = self.fallback.call(task, inp)
        return out, {"backend": "template-fallback", "model": None}


# ---------------------------------------------------------------------------- live backend
class LiveBackend:
    name = "live"

    def __init__(self, path: Path = RECORDINGS):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("LiveBackend needs ANTHROPIC_API_KEY")
        import anthropic  # lazy: template and recorded modes need no SDK
        self.client = anthropic.Anthropic()
        self.path = path

    def call(self, task: str, inp: dict) -> tuple[dict, dict]:
        model = config.TASK_MODEL[task]
        msg = self.client.messages.create(
            model=model, max_tokens=800, system=prompts.SYSTEM[task],
            messages=[{"role": "user", "content": prompts.user_message(task, inp)}])
        out = parse_json("".join(b.text for b in msg.content if getattr(b, "type", "") == "text"))
        self._record(task, inp, out, model)
        return out, {"backend": "live", "model": model}

    def _record(self, task: str, inp: dict, out: dict, model: str) -> None:
        data = json.loads(self.path.read_text()) if self.path.exists() else {"meta": {}, "recordings": {}}
        data["recordings"][task_key(task, inp)] = {"task": task, "model": model, "output": out}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")


def parse_json(text: str) -> dict:
    """Parse a model reply that should be a bare JSON object, tolerating code fences."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in model reply")
    return json.loads(t[start:end + 1])


def get_backend(name: str):
    return {"template": TemplateBackend, "recorded": RecordedBackend, "live": LiveBackend}[name]()
