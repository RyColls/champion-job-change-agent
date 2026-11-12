# Champion job-change agent

A proof of concept for an **event-driven agent with a human approval gate**. When someone who champions a
product changes jobs, the agent notices, decides what it means with plain rules, and queues work for two
teams: outreach for sales-assist at the person's new company, a risk flag for customer success at the old
account. Nothing goes to a prospect until a person approves it.

> **Everything here is fictional.** Cairnboard (a made-up product feedback tool), its customers, every
> person and every company are invented, and the 90-day job-change feed is simulated. There is no data
> provider, no real client and no live deployment. Nothing is ever sent: approvals go to a mock outbox.

- **Demo:** open `docs/index.html` (90-day replay, approval inbox, account view)
- **Case study:** `docs/case-study.html`
- **Design:** [DESIGN.md](DESIGN.md)

## How it works

```
event -> read -> match person -> where they went -> duplicate check -> watch list -> rules -> plays -> approval queue
                                                                                          \-> audit log (every event)
```

Code decides; models write. Rules, identity matching and the approval gate are deterministic code. Models do
four jobs, each fact-checked by code:

| Step | Model | Guard |
|---|---|---|
| Read a free-text announcement | Haiku | every value must appear verbatim in the text |
| Explain an identity decision | Sonnet | code made the decision; the model cannot change it |
| Summarize history with the product | Sonnet | checked against the record |
| Draft outreach | Sonnet | every claim must point at a record field, or the draft is blocked |

## Results (measured against an answer key the agent never reads)

Simulated data: 300 accounts, 1,500 contacts, 400 prospects, 5 competitors, 80 events per feed. Full per-feed
reports, including every failing event and why, are in `results/<feed>/<backend>/acceptance.md`.

| Test | First run (v1, `eval`) | Final (v2, `eval2`, fresh feed, recorded models) |
|---|---|---|
| 1 Detection, at least 52 of 55 | 48 of 55 (fail) | 48 of 55 (fail) |
| 2 Name collisions trigger 0 plays | 1 of 9 (fail) | 0 of 9 |
| 3 Duplicates create 0 second tasks | 0 of 4 | 0 of 4 |
| 4 Classification at least 95% | 90.0% (fail) | 91.2% (fail) |
| 5 Competitor moves get 0 drafts | 0 | 0 |
| 6 Old-account play on every real departure | 48 of 55 (fail) | 48 of 55 (fail) |
| 7 Draft integrity, 0 unsupported facts | 0 | 0, and 60 of 60 planted fake facts blocked |
| 8 Approval gate | pass | pass |
| 9 Audit trail for all 80 events | pass | pass |

**Why 1, 4 and 6 fail:** every miss was held in identity review instead of guessed at. Those events arrive with
no previous employer, so a real move and a look-alike stranger have identical evidence. Confirming them would
let strangers trigger plays. A provider-supplied profile ID would fix it; it is out of scope here.
v1 also let one name collision trigger a play; v2 fixes that, and the fix was checked on a feed generated
after it. The first-run results are in git history (commit `2ee645e`).

## Where the model outputs come from

Three interchangeable backends (`agent/ai.py`): `template` (deterministic, used by tests), `live` (calls the
Anthropic API with `claude-sonnet-5-5` and `claude-haiku-5-5`, needs `ANTHROPIC_API_KEY`), and `recorded`
(replays stored answers from `recordings/ai_recordings.json`). The build session had no API key, so the live
path is unit-tested against a fake client but **has not been run against the real API**. The recorded answers
were produced by Haiku and Sonnet subagents using the same system prompts as the live backend
(`agent/prompts.py`); `tools/` shows how they were exported and imported.

## Run it

```bash
pip install pytest
python -m pytest                                        # 46 unit tests
python datagen/generate.py --feed eval2                 # regenerate a feed (dev, eval, eval2)
python -m agent.cli --feed eval2 --backend template     # run the pipeline
python -m evals.run_acceptance --feed eval2 --backend template
python demo/build.py --feed eval2 --backend recorded    # rebuild docs/
# live models: ANTHROPIC_API_KEY=... pip install anthropic && python -m agent.cli --feed eval2 --backend live
```

## Layout

```
agent/     identity, rules, plays, verifier, approval queue, AI backends, pipeline
datagen/   seeded generator for the fictional data
data/      dev (seed 7), eval (seed 2026), eval2 (seed 4242, generated after the v2 fix)
evals/     acceptance tests, independent draft auditor, answer keys (the agent never reads these)
results/   decisions, audit logs, queues and acceptance reports per feed and backend
recordings/ stored model answers   tools/ export and import them   demo/ docs/  the demo and case study
```

The agent is tested with the answer key removed entirely (`tests/test_pipeline.py`).
