"""Collect every AI task a feed needs and write them out as batch files for a model to answer.

    python -m tools.export_ai_tasks --feed eval2 --out /tmp/batches [--chunk 40]

Used to RECORD real model answers when no API key is available in the session: a model answers each
batch using the same system prompt the live backend uses, and tools/import_ai_recordings.py stores the
answers so the pipeline can replay them (--backend recorded).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent import prompts
from agent.ai import RecordedBackend, TemplateBackend, task_key
from agent.pipeline import Pipeline

ROOT = Path(__file__).resolve().parent.parent


class Collect:
    def __init__(self, base):
        self.base, self.name, self.items = base, base.name, {}

    def call(self, task, inp):
        out, prov = self.base.call(task, inp)
        self.items.setdefault(task_key(task, inp), {"key": task_key(task, inp), "task": task, "input": inp,
                                                    "recorded": prov["backend"] == "recorded"})
        return out, prov


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--chunk", type=int, default=40)
    ap.add_argument("--only-missing", action="store_true")
    a = ap.parse_args()
    base = RecordedBackend() if a.only_missing else TemplateBackend()
    c = Collect(base)
    Pipeline(ROOT / "data" / a.feed, c).run()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    by_task: dict[str, list] = {}
    for it in c.items.values():
        if not (a.only_missing and it["recorded"]):
            by_task.setdefault(it["task"], []).append({"key": it["key"], "input": it["input"]})
    for task, items in sorted(by_task.items()):
        for i in range(0, len(items), a.chunk):
            f = out / f"{task}_{i // a.chunk + 1}.json"
            f.write_text(json.dumps({"task": task, "system": prompts.SYSTEM[task], "items": items[i:i + a.chunk]},
                                    indent=1, ensure_ascii=False))
            print(f"{f.name}: {len(items[i:i + a.chunk])} items")


if __name__ == "__main__":
    main()
