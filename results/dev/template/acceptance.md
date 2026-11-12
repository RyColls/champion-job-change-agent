# Acceptance results: dev feed

Backend for the AI steps: `template`. Measured against the answer key in this project on simulated, fictional data. 6 of 9 tests pass.

| # | Test | Pass condition | Measured | Result |
|---|---|---|---|---|
| 1 | Detection | At least 52 of the 55 real departures are caught | 50 of 55 caught; 5 of the 5 missed were held in identity review (not counted as caught) | **FAIL** |
| 2 | Name collisions | 0 of 9 trigger any play | 0 of 9 triggered a play; outcomes {'no_match': 7, 'identity_review': 2} | PASS |
| 3 | Duplicates | 0 of 4 create a second task | 0 of 4 created a second task | PASS |
| 4 | Classification | At least 95% of events match the answer key | 75 of 80 match (93.8%) | **FAIL** |
| 5 | Competitor suppression | 0 outreach drafts for the 5 competitor moves | 0 drafts for 5 competitor moves; 5 were explicitly suppressed (the rest were held before reaching the rules) | PASS |
| 6 | Old-account play | Fires on every real departure, with the correct days until renewal | 50 of 55 fired with the correct days until renewal | **FAIL** |
| 7 | Draft integrity | 0 facts in any draft that are not in the record | (a) independent audit of 27 queued drafts and summaries: 0 unsupported facts; (b) planted-fact tests: agent verifier blocked 60 of 60, independent audit flagged 60 of 60; first-pass blocks 0 of 27 drafts, 0 blocked after retry | PASS |
| 8 | Approval gate | Nothing leaves the queue without a human action | 27 drafts left pending by the pipeline; outbox empty until a named human acted; direct sends refused; unapproved sends refused: 2 of 2 | PASS |
| 9 | Audit trail | Every one of the 80 events shows each decision and the rule behind it | 80 of 80 events have all 7 steps with a rule and detail | PASS |

## Test 1: Detection

- event_id: E021, type: moved_fit, noise: ['prior_employer_missing', 'prior_title_missing'], why: held in identity review: score 4.0 is below the confirm threshold (name +3.0, employer +0.0, city +1.0)
- event_id: E031, type: moved_customer, noise: ['prior_employer_missing'], why: held in identity review: score 4.0 is below the confirm threshold (name +3.0, employer +0.0, city +1.0)
- event_id: E053, type: moved_fit, noise: ['prior_title_missing'], why: held in identity review: score 4.0 is below the confirm threshold (name +3.0, employer +0.0, city +1.0)
- event_id: E066, type: moved_fit, noise: ['prior_employer_missing'], why: held in identity review: score 5.0 is below the confirm threshold (name +3.0, employer +0.0, city +1.0, title +1.0)
- event_id: E068, type: moved_nofit, noise: ['prior_title_missing'], why: held in identity review: score 4.0 is below the confirm threshold (name +3.0, employer +0.0, city +1.0)

## Test 4: Classification

- event_id: E021, type: moved_fit, expected: departure:fit_prospect, got: identity_review, why: held in identity review: score 4.0 is below the confirm threshold (name +3.0, employer +0.0, city +1.0)
- event_id: E031, type: moved_customer, expected: departure:customer, got: identity_review, why: held in identity review: score 4.0 is below the confirm threshold (name +3.0, employer +0.0, city +1.0)
- event_id: E053, type: moved_fit, expected: departure:fit_prospect, got: identity_review, why: held in identity review: score 4.0 is below the confirm threshold (name +3.0, employer +0.0, city +1.0)
- event_id: E066, type: moved_fit, expected: departure:fit_prospect, got: identity_review, why: held in identity review: score 5.0 is below the confirm threshold (name +3.0, employer +0.0, city +1.0, title +1.0)
- event_id: E068, type: moved_nofit, expected: departure:nofit_prospect, got: identity_review, why: held in identity review: score 4.0 is below the confirm threshold (name +3.0, employer +0.0, city +1.0)

## Test 6: Old-account play

_Strict: departures held in identity review count as failures here._

- event_id: E021, why: no risk flag: held in identity review: score 4.0 is below the confirm threshold (name +3.0, employer +0.0, city +1.0)
- event_id: E031, why: no risk flag: held in identity review: score 4.0 is below the confirm threshold (name +3.0, employer +0.0, city +1.0)
- event_id: E053, why: no risk flag: held in identity review: score 4.0 is below the confirm threshold (name +3.0, employer +0.0, city +1.0)
- event_id: E066, why: no risk flag: held in identity review: score 5.0 is below the confirm threshold (name +3.0, employer +0.0, city +1.0, title +1.0)
- event_id: E068, why: no risk flag: held in identity review: score 4.0 is below the confirm threshold (name +3.0, employer +0.0, city +1.0)

## Test 7: Draft integrity

_The verifier checks entities, numbers, quantities and outcome language. It cannot verify arbitrary lowercase prose claims; those are limited by the prompt and by human review._


## Test 8: Approval gate

_The outbox is a mock. Nothing real is ever sent._

