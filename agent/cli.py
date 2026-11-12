"""Run the pipeline on a feed and write results.

    python -m agent.cli --feed eval --backend template
    python -m agent.cli --feed eval --backend recorded
    ANTHROPIC_API_KEY=... python -m agent.cli --feed eval --backend live
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .ai import get_backend
from .pipeline import Pipeline

ROOT = Path(__file__).resolve().parent.parent


def run_feed(feed: str, backend_name: str, results_dir: Path | None = None) -> dict:
    backend = get_backend(backend_name)
    res = Pipeline(ROOT / "data" / feed, backend).run()
    res["backend"] = backend_name
    out = results_dir or ROOT / "results" / feed / backend_name
    out.mkdir(parents=True, exist_ok=True)
    for name in ("decisions", "flags", "tasks", "queue", "notifications", "record_updates", "new_contacts",
                 "suppressions", "stats"):
        (out / f"{name}.json").write_text(json.dumps(res[name], indent=1, ensure_ascii=False) + "\n",
                                          encoding="utf-8")
    with (out / "audit_log.jsonl").open("w", encoding="utf-8") as f:
        for d in res["decisions"]:
            f.write(json.dumps({"event_id": d["event_id"], "label": d["label"], "steps": d["steps"]},
                               ensure_ascii=False) + "\n")
    (out / "run.json").write_text(json.dumps({"feed": feed, "backend": backend_name,
                                              "events": len(res["decisions"])}, indent=1) + "\n")
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", choices=["dev", "eval"], required=True)
    ap.add_argument("--backend", choices=["template", "recorded", "live"], default="template")
    a = ap.parse_args()
    res = run_feed(a.feed, a.backend)
    labels: dict[str, int] = {}
    for d in res["decisions"]:
        labels[d["label"]] = labels.get(d["label"], 0) + 1
    print(f"feed={a.feed} backend={a.backend} events={len(res['decisions'])}")
    for k, v in sorted(labels.items()):
        print(f"  {v:3d}  {k}")
    print("stats:", json.dumps(res["stats"]))


if __name__ == "__main__":
    main()
