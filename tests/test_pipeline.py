import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from agent.ai import TemplateBackend
from agent.pipeline import STEPS, Pipeline

ROOT = Path(__file__).resolve().parent.parent
FEEDS = ["dev", "eval", "eval2"]


@pytest.mark.parametrize("feed", FEEDS)
def test_data_matches_the_spec(feed):
    d = ROOT / "data" / feed
    n = {f: len(json.loads((d / f"{f}.json").read_text())) for f in
         ("accounts", "contacts", "prospects", "competitors", "events")}
    assert n == {"accounts": 300, "contacts": 1500, "prospects": 400, "competitors": 5, "events": 80}
    key = json.loads((ROOT / "evals" / "keys" / f"{feed}.json").read_text())["events"]
    kinds = {}
    for k in key.values():
        kinds[k["type"]] = kinds.get(k["type"], 0) + 1
    assert kinds == {"moved_fit": 30, "moved_customer": 6, "moved_competitor": 5, "moved_nofit": 6,
                     "moved_unknown": 3, "left": 5, "title_change": 12, "collision": 9, "duplicate": 4}
    assert sum(1 for k in key.values() if k["real_departure"]) == 55


@pytest.mark.parametrize("feed", FEEDS)
def test_events_never_carry_truth(feed):
    ev = json.loads((ROOT / "data" / feed / "events.json").read_text())
    for e in ev:
        assert set(e) <= {"event_id", "received_at", "source", "format", "structured", "text"}


def test_pipeline_is_deterministic():
    a = Pipeline(ROOT / "data" / "dev", TemplateBackend()).run()
    b = Pipeline(ROOT / "data" / "dev", TemplateBackend()).run()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_every_event_has_every_step_and_a_rule():
    res = Pipeline(ROOT / "data" / "dev", TemplateBackend()).run()
    assert len(res["decisions"]) == 80
    for d in res["decisions"]:
        assert [s["step"] for s in d["steps"]] == STEPS
        assert all(s["rule"] and s["detail"] for s in d["steps"])


def test_pipeline_never_advances_anything_past_pending():
    res = Pipeline(ROOT / "data" / "dev", TemplateBackend()).run()
    assert {q["status"] for q in res["queue"]} <= {"pending", "needs_manual_draft"}


def test_one_risk_flag_per_departed_contact():
    res = Pipeline(ROOT / "data" / "dev", TemplateBackend()).run()
    keys = [(f["account_id"], f["departed_contact_id"]) for f in res["flags"]]
    assert len(keys) == len(set(keys))


def test_agent_runs_with_the_answer_key_removed(tmp_path):
    """Isolation: copy only agent/ and data/dev into an empty tree (no evals/ at all) and run it."""
    shutil.copytree(ROOT / "agent", tmp_path / "agent", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "data" / "dev", tmp_path / "data" / "dev")
    r = subprocess.run([sys.executable, "-m", "agent.cli", "--feed", "dev", "--backend", "template"],
                       cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert not (tmp_path / "evals").exists()
    same = json.loads((tmp_path / "results/dev/template/decisions.json").read_text())
    ref = Pipeline(ROOT / "data" / "dev", TemplateBackend()).run()["decisions"]
    assert [d["label"] for d in same] == [d["label"] for d in ref]
