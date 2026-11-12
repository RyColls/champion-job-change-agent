import json
import sys
import types

import pytest

from agent import ai, config


def test_models_are_routed_sonnet_for_judgement_haiku_for_extraction():
    assert config.TASK_MODEL["normalize"] == config.MODEL_HAIKU
    for t in ("explain_identity", "history_summary", "draft_outreach"):
        assert config.TASK_MODEL[t] == config.MODEL_SONNET


def test_parse_json_tolerates_code_fences():
    assert ai.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert ai.parse_json('Here you go: {"a": 1}') == {"a": 1}
    with pytest.raises(ValueError):
        ai.parse_json("no json here")


def test_template_normalizer_handles_every_announcement_template():
    tb = ai.TemplateBackend()
    cases = [
        ("Kate Ramos has joined Cobaltgrid as Head of Product. Previously Senior PM at Lumenforge Inc. Based in Austin.",
         "Kate Ramos", "Cobaltgrid", "Head of Product", "Lumenforge Inc"),
        ("Thrilled to share I'm starting a new chapter as VP Product at Cobaltgrid! After a great run at Lumenforge, "
         "onward. — Kate Ramos, Austin", "Kate Ramos", "Cobaltgrid", "VP Product", "Lumenforge"),
        ("Kate Ramos has left Lumenforge, where they were Product Manager. No new role announced.",
         "Kate Ramos", None, None, "Lumenforge"),
        ("Congratulations to Kate Ramos, now Head of Product at Lumenforge (formerly Product Manager).",
         "Kate Ramos", "Lumenforge", "Head of Product", None),
    ]
    for text, name, new_emp, new_title, prior in cases:
        out, _ = tb.call("normalize", {"text": text})
        assert (out["full_name"], out["new_employer"], out["new_title"], out["prior_employer"]) == \
               (name, new_emp, new_title, prior), text


def test_live_backend_uses_the_configured_model_and_records(tmp_path, monkeypatch):
    calls = []

    class Block:
        type = "text"
        text = '{"summary": "ok"}'

    class Client:
        class messages:
            @staticmethod
            def create(**kw):
                calls.append(kw)
                return types.SimpleNamespace(content=[Block()])

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=lambda: Client()))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    rec = tmp_path / "rec.json"
    live = ai.LiveBackend(rec)
    out, prov = live.call("history_summary", {"facts": {"a": "b"}})
    assert out == {"summary": "ok"} and prov == {"backend": "live", "model": config.MODEL_SONNET}
    assert calls[0]["model"] == config.MODEL_SONNET
    # and the recording can be replayed
    rb = ai.RecordedBackend(rec)
    out2, prov2 = rb.call("history_summary", {"facts": {"a": "b"}})
    assert out2 == {"summary": "ok"} and prov2["backend"] == "recorded"
    assert json.loads(rec.read_text())["recordings"]


def test_recorded_backend_falls_back_and_says_so(tmp_path):
    rb = ai.RecordedBackend(tmp_path / "missing.json")
    out, prov = rb.call("history_summary", {"facts": {
        "contact.full_name": "A B", "contact.role_label": "champion", "account.name": "X", "account.plan": "Team",
        "account.usage_level": "low", "account.customer_since": "2024-01-01", "contact.signup_date": "2024-01-02",
        "contact.boards_created": "3", "contact.last_active_date": "2026-07-01"}})
    assert prov["backend"] == "template-fallback" and rb.misses == 1


def test_live_backend_requires_a_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        ai.LiveBackend()
