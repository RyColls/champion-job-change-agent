# Champion Job-Change Agent: design

A portfolio proof of concept. Cairnboard is a **fictional sample client**; every company, account,
contact and event in this repo is synthetic. The job-change feed is **simulated**. Nothing here is a
live deployment and no real person's data is used.

## 1. What it is

An event-driven workflow agent with a human approval gate. One event type (a contact's employment
changed) comes in; code verifies it, classifies it and picks up to two plays from a fixed rules
table; AI writes three things; a person approves before anything leaves.

```
event -> normalize -> dedupe -> verify identity -> classify destination -> rules -> plays -> approval queue
                                                                                   \-> audit log (every event, including no-action)
```

Where AI is used (and only here):

| Step | Model | Job | Guard in code |
|---|---|---|---|
| Normalize free-text events | Haiku | Pull employer, title, start date out of a free-text announcement | Every extracted value must appear in the source text, else the event goes to review |
| Identity explanation | Sonnet | Explain in plain words why two records are or are not the same person | The match decision is a code score. The model explains it and cannot change it |
| History summary | Sonnet | Summarize the person's history with Cairnboard for the rep | Built only from the fact sheet; checked by the same verifier as drafts |
| Outreach draft | Sonnet | Draft the outreach message | Model returns claims with field references; code checks every claim and scans the body; failures are blocked |

Model IDs live in `agent/config.py`: `claude-sonnet-5-5` and `claude-haiku-5-5`.

## 2. Scenario (fictional)

Cairnboard: product feedback and roadmap tool for B2B software teams. 3,000 paying companies, about
41,000 named users, Series C, 350 employees, product-led with a 12-person sales-assist team and 8
customer success managers, $18,000 average contract. Economic buyer: Head of Product. Champions:
product managers and product operations leads. Sponsor: Tomás Echeverría, Director of Revenue
Operations (fictional).

Starting conditions of the scenario (not results): about 1 in 5 champions changes jobs each year;
4 of the 10 largest churned accounts lost their champion 60 to 120 days before renewal; 11 deals
came from former champions and closed at 36% against 13% for cold outbound.

## 3. Rules (code, deterministic, owned by RevOps)

| Rule ID | Where the person went | New-company play | Old-account play |
|---|---|---|---|
| R1 | A company that fits and is not a customer | Create contact, carry over history, draft outreach for approval | Risk flag and task for the CSM |
| R2 | An existing customer | Notify the account manager | Risk flag and task |
| R3 | A competitor | None. Outreach is suppressed and the event is logged | Risk flag and task |
| R4 | A company that does not fit | Log only | Risk flag and task |
| R5 | No new employer known | None | Risk flag and task |
| R6 | Same company, new title | Update the record | None |
| R7 | Unknown company (not in customers, prospects or competitors) | Log only, flag for RevOps review | Risk flag and task |

Guard rules, applied before R1 to R7:

| Rule ID | Guard |
|---|---|
| G1 | Duplicate of an earlier event (same contact, same normalized new employer, within 45 days): log, no second task |
| G2 | Identity score below the no-match threshold: no action, log |
| G3 | Identity score in the review band: no play; goes to a human identity-review queue |
| G4 | Watch list: only champions and executive sponsors are monitored. A move by an admin or power user is logged with no play |
| G5 | Normalization failed validation: no play; goes to review |

R7, G3 and G4 are additions to the original charter, made to close gaps in it.

Old-account play details: `days_until_renewal = account.renewal_date - event.received_at` (calendar
days). Risk level: high if 120 days or fewer, medium if 121 to 240, low otherwise. Next-best
contacts are ranked in code from the remaining contacts on the account (role, usage, recency), each
with a stated reason.

## 4. Synthetic data

Seeded generator (`datagen/generate.py`). Two feeds:

- `dev` (seed 7): used to build and tune thresholds.
- `eval` (seed 2026): held out. Acceptance results are measured on this feed only.

Each feed: 300 customer accounts (plan, renewal date, usage level, CSM, account manager), 1,500
contacts (role: champion, admin, power user, executive sponsor), 400 prospect companies (ICP fit
yes/no), 5 competitors, and a 90-day feed of 80 events:

| Event type | Count | Correct handling |
|---|---|---|
| Moved to a fitting company that is not a customer | 30 | Both plays |
| Moved to an existing customer | 6 | Notify account manager, old-account play |
| Moved to a competitor | 5 | Suppress outreach, old-account play |
| Moved to a company that does not fit | 9 | Log, old-account play |
| Left with no new employer | 5 | Old-account play only |
| New title at the same company | 12 | Update record, no play |
| Name collision: a different person with the same name | 9 | No action |
| Duplicate of an earlier event | 4 | No second task |

55 real departures = 30 + 6 + 5 + 9 + 5. All 80 events concern watch-listed contacts (champions and
executive sponsors) so the charter's counts hold; G4 is covered by unit tests.

The answer key is written to `evals/keys/<feed>.json`. Nothing under `agent/` may read `evals/`.

The feed must be hard enough that a perfect score would be surprising:

- True moves carry realistic noise: nicknames (Katherine/Kate), a changed surname, employer-name
  variants ("Inc.", "Labs", abbreviations), title drift, a changed city, missing fields.
- Name collisions range from easy (different employer, different city) to hard (same name, same
  city, similar title; one or two with a similar or identical prior employer name).
- Some events arrive as free text ("Thrilled to share I've joined ... as ...") instead of
  structured rows.
- Some of the 9 "does not fit" moves go to companies not in any list (R7).
- Duplicates include at least one with a variant employer name and a shifted date.
- Email domains use the reserved `.example` TLD. Company names are invented compounds.

## 5. Acceptance tests (run against the eval answer key, all results published)

| # | Test | Pass condition |
|---|---|---|
| 1 | Detection | At least 52 of the 55 real departures are caught |
| 2 | Name collisions | 0 of 9 trigger any play |
| 3 | Duplicates | 0 of 4 create a second task |
| 4 | Classification | At least 95% of events match the answer key |
| 5 | Competitor suppression | 0 outreach drafts for the 5 competitor moves |
| 6 | Old-account play | Fires on every real departure, with the correct days until renewal |
| 7 | Draft integrity | 0 facts in any draft that are not in the record |
| 8 | Approval gate | Nothing leaves the queue without a human action |
| 9 | Audit trail | Every one of the 80 events shows each decision and the rule behind it |

Scoring definitions, fixed before the eval run:

- "Caught" (test 1) = auto-confirmed. Events held in identity review are reported separately and do
  **not** count as caught.
- Test 6 is strict: a real departure held in review or missed counts as a failure.
- Test 7 has two parts: (a) the queued drafts, audited by an independent checker in `evals/` that
  does not share code with the agent's verifier; (b) planted-fact tests proving the verifier blocks
  fabricated facts. First-pass block counts are reported.
- For any failed test, the failing events are listed with an explanation.

## 6. Presentation

Static demo (built into `docs/`) with three views: a 90-day replay, an approval inbox, an account
view. It replays committed pipeline output; there is no API key in the browser.

Wording rules for anything public: say "a fictional sample client" near the top; call the numbers in
section 2 "the sample client's starting point"; call the feed "simulated job-change events"; present
test results as measured in this project against the answer key, with counts. Never claim churn
prevented, pipeline generated, revenue, a named data-provider integration, or a live deployment.

## 7. Identity scoring (code, agent/identity.py)

| Signal | Points |
|---|---|
| Full name matches exactly | +3.0 |
| First name is a known variant, surname matches | +2.5 |
| First name matches, surname differs | +0.5 (v2; needs corroboration) |
| Prior employer resolves to the contact's account | +3.0 |
| Prior employer close to the account name | +1.5 |
| Prior employer is something else | -3.0 |
| No prior employer, but the new employer is the same account (a new title) | +3.0 |
| Prior e-mail domain matches / does not match the account | +3.0 / -4.0 |
| Location matches | +1.0 (a different city is not penalised: people relocate) |
| Prior title similar | +1.0 (dissimilar: -0.5) |

Score 6.0 or more confirms (rule I1). From 3.5 up to 6.0 the event is held for a person (G3). Below 3.5
it is a different person (G2). Two candidates within 1.0 point of each other are held for a person.

## 8. Changes since the first measured run

- **v1** was measured first on the `eval` feed: 5 of 9 tests passed and name collision E068 triggered a play (git commit 2ee645e).
- **v2** lowers the weight of a surname mismatch (it let a colleague with the same first name be matched as a surname change). It was then measured on `eval2`, a feed generated after the fix.
- The generator's renewal dates were shifted so they always fall after the feed (they could precede the event). Only that field changed.
- The fact checker gained a possessive fix and a no-pronoun rule (the record has no gender).

## 9. Known limitations

- Events with no prior employer are held for review, so detection, classification and the old-account play miss them. A provider-supplied profile identifier would resolve this.
- The offline normalizer parses only the announcement templates the simulator produces. The Haiku outputs match it on every announcement in `eval2`, which shows the recorded model handled these, not that arbitrary text is solved.
- The fact checker cannot verify arbitrary lowercase prose claims.
- The live backend is unit-tested against a fake client and has not been run against the real API in this repository's build session (no key was available).
