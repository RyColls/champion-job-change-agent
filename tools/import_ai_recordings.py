"""Validate and store model answers so the recorded backend can replay them.

    python -m tools.import_ai_recordings --task draft_outreach --model "<label>" answers.json

answers.json is {"<key>": {...output...}, ...}. Anything with the wrong shape is rejected, not stored.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent.ai import RECORDINGS

SHAPES = {
    "normalize": lambda o: set(o) >= {"full_name", "prior_employer", "prior_title", "new_employer", "new_title",
                                      "location"},
    "explain_identity": lambda o: isinstance(o.get("explanation"), str) and o["explanation"].strip(),
    "history_summary": lambda o: isinstance(o.get("summary"), str) and o["summary"].strip(),
    "draft_outreach": lambda o: isinstance(o.get("subject"), str) and isinstance(o.get("body"), str)
    and isinstance(o.get("claims"), list)
    and all(isinstance(c, dict) and {"text", "field"} <= set(c) for c in o["claims"]),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True, choices=sorted(SHAPES))
    ap.add_argument("--model", required=True)
    ap.add_argument("answers")
    ap.add_argument("--expect", help="batch file the answers belong to; every key in it must be answered")
    a = ap.parse_args()
    answers = json.loads(Path(a.answers).read_text())
    if a.expect:
        want = {i["key"] for i in json.loads(Path(a.expect).read_text())["items"]}
        missing = want - set(answers)
        print(f"expected {len(want)}, answered {len(want & set(answers))}, missing {len(missing)}")
    data = json.loads(RECORDINGS.read_text()) if RECORDINGS.exists() else {"meta": {}, "recordings": {}}
    ok = bad = 0
    for k, out in answers.items():
        if isinstance(out, dict) and SHAPES[a.task](out):
            data["recordings"][k] = {"task": a.task, "model": a.model, "output": out}
            ok += 1
        else:
            bad += 1
            print("rejected (bad shape):", k)
    data["meta"] = {"note": "Answers recorded from Claude Code subagents (not direct API calls), using the same "
                            "system prompts as the live backend (agent/prompts.py).",
                    **data.get("meta", {})}
    RECORDINGS.parent.mkdir(parents=True, exist_ok=True)
    RECORDINGS.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"stored {ok}, rejected {bad}, total recordings {len(data['recordings'])}")


if __name__ == "__main__":
    main()
