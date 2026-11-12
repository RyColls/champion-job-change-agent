"""Build the static demo (docs/index.html) and the case-study page (docs/case-study.html).

    python demo/build.py --feed eval2 --backend recorded

Every number on both pages is read from results/<feed>/<backend>/ at build time, so the pages cannot
drift from the measured results. The only hard-coded figures are the first-run (v1) results, which
are pinned to git commit 2ee645e where the result files can be inspected.
"""
from __future__ import annotations

import argparse
import html
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from agent import config  # noqa: E402
from agent.rules import GUARDS, RULES  # noqa: E402

REPO = "https://github.com/RyColls/champion-job-change-agent"
DOCS = ROOT / "docs"

# Agent v1 on the eval feed, the first time it was measured (git show 2ee645e:results/eval/template/acceptance.md)
RUN1 = {1: "48 of 55", 2: "1 of 9", 3: "0 of 4", 4: "72 of 80 (90.0%)", 5: "0 drafts", 6: "48 of 55",
        7: "0 unsupported facts", 8: "nothing sent without a human", 9: "80 of 80"}
RUN1_PASS = {1: False, 2: False, 3: True, 4: False, 5: True, 6: False, 7: True, 8: True, 9: True}

RULE_TEXT = {
    "N1": "Structured event, no model needed", "N2": "Free-text event: a model extracted the fields and every value "
    "was found verbatim in the text", "I1": f"Identity score met the confirm threshold ({config.CONFIRM_THRESHOLD})",
    "C1": "Destination classified against the customer, prospect and competitor lists",
    "D1": "First time this person and destination were seen", "W1": "Contact is a champion or executive sponsor",
    "X1": "Final label recorded", **GUARDS, **{k: v[4] for k, v in RULES.items()},
}
ROLE_LABEL = {"champion": "Champion", "exec_sponsor": "Executive sponsor", "admin": "Admin", "power_user": "Power user"}


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def esc(s) -> str:
    return html.escape(str(s))


def build_demo(feed: str, backend: str) -> None:
    res, data = ROOT / "results" / feed / backend, ROOT / "data" / feed
    decisions = load(res / "decisions.json")
    flags, queue = load(res / "flags.json"), load(res / "queue.json")
    contacts = {c["id"]: c for c in load(data / "contacts.json")}
    accounts = {a["id"]: a for a in load(data / "accounts.json")}
    need_c = {f["departed_contact_id"] for f in flags} | {q["contact_id"] for q in queue if q.get("contact_id")}
    slim_dec = [{k: d[k] for k in ("event_id", "received_at", "label", "rule", "plays", "steps", "payload") if k in d}
                for d in decisions]
    for q in queue:
        q.pop("facts_used", None)
    payload = {
        "feed": feed, "backend": backend, "rules": RULE_TEXT, "rolelabel": ROLE_LABEL,
        "events": load(data / "events.json"), "decisions": slim_dec, "flags": flags, "tasks": load(res / "tasks.json"),
        "queue": queue, "notifications": load(res / "notifications.json"),
        "record_updates": load(res / "record_updates.json"), "suppressions": load(res / "suppressions.json"),
        "accounts": {f["account_id"]: {k: accounts[f["account_id"]][k] for k in ("customer_since", "usage_level")}
                     for f in flags},
        "contacts": {c: {k: contacts[c][k] for k in ("full_name", "title", "role")} for c in need_c},
    }
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    DOCS.mkdir(exist_ok=True)
    (DOCS / "index.html").write_text((ROOT / "demo" / "template.html").read_text(encoding="utf-8")
                                     .replace("__DATA__", blob), encoding="utf-8")
    shutil.copy(ROOT / "demo" / "style.css", DOCS / "style.css")


def tests_table(acc: dict) -> str:
    rows = []
    for t in acc["tests"]:
        v1 = RUN1[t["n"]]
        c1 = "pass" if RUN1_PASS[t["n"]] else "fail"
        c2 = "pass" if t["passed"] else "fail"
        rows.append(f"<tr><td>{t['n']}. {esc(t['name'])}</td><td>{esc(t['condition'])}</td>"
                    f"<td class='{c1}'>{esc(v1)}</td><td class='{c2}'>{esc(t['short'])}</td></tr>")
    return ("<table class='t'><tr><th>Test</th><th>Pass condition</th><th>First run on the eval feed</th>"
            "<th>Final agent on a fresh feed</th></tr>" + "".join(rows) + "</table>")


def all_runs_table() -> str:
    rows = []
    for feed in ("dev", "eval", "eval2"):
        for backend in ("template", "recorded"):
            p = ROOT / "results" / feed / backend / "acceptance.json"
            if p.exists():
                a = load(p)
                failed = ", ".join(str(t["n"]) for t in a["tests"] if not t["passed"]) or "none"
                rows.append(f"<tr><td>{feed}</td><td>{backend}</td><td>{a['passed']} of 9</td><td>{failed}</td></tr>")
    return ("<table class='t'><tr><th>Feed</th><th>AI steps</th><th>Tests passed</th><th>Failing tests</th></tr>"
            + "".join(rows) + "</table>")


def build_case(feed: str, backend: str) -> None:
    acc = load(ROOT / "results" / feed / backend / "acceptance.json")
    comp = acc["extra"]["identity_review_composition"]
    comp_txt = ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in comp.items())
    n_rev = sum(comp.values())
    t1 = next(t for t in acc["tests"] if t["n"] == 1)
    st = load(ROOT / "results" / feed / backend / "stats.json")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Champion job-change agent: case study</title>
<meta name="description" content="Case study: an event-driven agent that notices when a champion changes jobs, with a human approval gate. Fictional sample client, simulated events.">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,600&family=Schibsted+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="style.css"></head><body>
<div class="notice"><b>A fictional sample client.</b> Cairnboard, its sponsor persona Tomás Echeverría (Director of Revenue Operations), and every account and contact are invented. The job-change events are simulated.</div>
<main class="doc">
<h1>An agent that notices when a champion changes jobs</h1>
<p class="lede">When someone who champions your product leaves a customer, a renewal is at risk and the person is a warm lead at their next company. This proof of concept catches that moment, decides what it means with plain rules, and puts a human in front of every message before it goes anywhere.</p>
<p><a href="index.html">Open the interactive demo</a> · <a href="{REPO}">Read the code</a></p>

<h2>The sample client's starting point</h2>
<p>These are the scenario's starting conditions, not results from this project. Cairnboard is a fictional product feedback and roadmap tool with 3,000 paying companies, about 41,000 named users and an average contract of $18,000 a year.</p>
<ul>
<li>About 1 in 5 champions changes jobs each year, roughly 600 moves across 3,000 customers.</li>
<li>4 of the 10 largest accounts that churned last year had lost their champion 60 to 120 days before renewal, and nobody knew.</li>
<li>11 deals last year came from former champions who brought Cairnboard to a new employer. They closed at 36%, against 13% for cold outbound.</li>
<li>No system tracked any of this. Customer success managers found out when an email bounced.</li>
</ul>

<h2>What the agent does</h2>
<p>One event type comes in: a contact's employment changed. Code verifies it and decides what to do. A model writes three things. A person approves every message.</p>
<ol class="flow"><li>Read the event</li><li class="ai">Match the person</li><li>Where they went</li><li>Duplicate check</li><li>Watch list</li><li>Rules</li><li class="ai">Draft and fact-check</li><li>Human approval</li></ol>
<p>Rules decide the play, in code, the same way every time, and revenue operations owns them. When the person joined a company that fits and is not a customer, the agent creates the contact, carries over their history and drafts outreach for a rep. When they left a customer account, it raises a risk flag with days until renewal, suggests next contacts and opens a task for the customer success manager. Competitors suppress outreach, and every event, including the ones that led to no action, is logged with the rule behind each decision.</p>

<h3>Where the models are used</h3>
<table class="t"><tr><th>Step</th><th>Model</th><th>What it does</th><th>What stops it going wrong</th></tr>
<tr><td>Read free-text announcements</td><td>Haiku</td><td>Pulls employer, title and name out of a sentence</td><td>Every extracted value must appear verbatim in the text</td></tr>
<tr><td>Explain an identity decision</td><td>Sonnet</td><td>Says in plain words why two records are or are not the same person</td><td>Code made the decision; the model only explains it</td></tr>
<tr><td>Summarize history</td><td>Sonnet</td><td>Summarizes what the person did with Cairnboard</td><td>Fact-checked against the record, no pronouns or invented numbers</td></tr>
<tr><td>Draft outreach</td><td>Sonnet</td><td>Writes the message for a rep to review</td><td>Every claim must match a record field or the draft is blocked</td></tr></table>

<h2>What was measured</h2>
<p>The nine acceptance tests ran against an answer key the agent never sees, on simulated data: 300 accounts, 1,500 contacts, 400 prospects, 5 competitors and a 90-day feed of 80 events. These are real counts from this project, passes and failures alike.</p>
{tests_table(acc)}
<p>The final agent was measured on a feed generated after the fix described below, so nothing about it was tuned on that feed. The fact checker blocked {st['drafts_blocked_first_pass']} of {st['drafts']} model-written drafts on the first pass and {st['summaries_failed_check']} of {st['drafts']} summaries failed its check (see “How the model outputs were produced”).</p>
{all_runs_table()}

<h2>What failed, and why</h2>
<div class="note"><p><b>The first run on the eval feed passed 5 of 9 tests and one name collision triggered a play.</b> A different person with the same first name, at the same customer as a known contact, was matched as a surname change. A surname mismatch alone now carries too little weight to confirm a match, and the fix was checked on a new feed rather than tuned on the one that exposed it. The first-run results are kept in the repository history.</p></div>
<p><b>Detection stays below its target:</b> {esc(t1['short'])} real departures were caught, against a target of at least 52. Every miss was held in identity review rather than guessed at. These events arrive without a previous employer, so the only evidence is a name, a city and sometimes a title. Real moves and look-alike strangers produce the same evidence. The review queue on this feed held {n_rev} events: {esc(comp_txt)}. Lowering the confirm threshold to catch more real moves would also let strangers trigger plays, so the agent holds them for a person. Detection, classification and the old-account play all fail for this one reason, because events held in review never reach the rules.</p>
<p><b>What would fix it:</b> a stable profile identifier from a data provider, or a second corroborating field such as the previous e-mail domain on every event. Neither is part of this proof of concept.</p>

<h2>What changed after the first run</h2>
<ul><li><b>Identity rule.</b> A surname mismatch can no longer confirm a match by itself (described above).</li>
<li><b>Generator.</b> The first version could give an account a renewal date earlier than the departure, which produced negative days until renewal in the demo. Renewal dates are now always after the feed. This changed only that field, so the first-run counts above are unaffected.</li>
<li><b>Fact checker.</b> It wrongly flagged a possessive form of a name from the record, and it now also blocks gendered pronouns, because the record has no gender.</li></ul>

<h2>How the model outputs were produced</h2>
<p>The agent has three interchangeable backends: a deterministic template backend used by tests, a live backend that calls the Anthropic API with the models above, and a recorded backend that replays stored model answers. The build session had no API key, so the live path is covered by unit tests against a fake client and has not run against the real API. The model answers behind the published results were produced by Claude Haiku and Sonnet subagents given the same system prompts as the live backend, then stored and replayed. Each queued draft shows which backend wrote it. One batch of summaries was rewritten after the first attempt turned out to be script-generated, and a no-pronoun rule was added after a draft inferred gender from a name.</p>

<h2>What this does not show</h2>
<ul><li>Any real client, real data or live deployment.</li><li>Any business outcome. No churn was prevented and no pipeline was generated.</li><li>A connection to a data provider. The feed is simulated.</li><li>That the fact checker catches everything. It checks entities, numbers, quantities, pronouns and outcome language. It cannot verify arbitrary lowercase prose, which is why a person reviews every draft.</li></ul>

<h2>Run it</h2>
<p><code>pip install pytest</code>, then <code>python -m pytest</code> for the unit tests, <code>python -m agent.cli --feed eval2 --backend template</code> to run the pipeline, and <code>python -m evals.run_acceptance --feed eval2 --backend template</code> for the nine tests. The design is in <a href="{REPO}/blob/main/DESIGN.md">DESIGN.md</a>.</p>
<footer>Built as a portfolio project. Cairnboard is a fictional company.</footer>
</main></body></html>"""
    (DOCS / "case-study.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", default="eval2")
    ap.add_argument("--backend", default="recorded")
    a = ap.parse_args()
    build_demo(a.feed, a.backend)
    build_case(a.feed, a.backend)
    print("built docs/index.html and docs/case-study.html from", a.feed, a.backend)
