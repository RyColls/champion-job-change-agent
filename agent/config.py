"""All tunables in one place. Thresholds were chosen on the `dev` feed, never on `eval`."""

# Models used by the AI steps. Sonnet does the judgement/writing work, Haiku does cheap extraction.
MODEL_SONNET = "claude-sonnet-5-5"
MODEL_HAIKU = "claude-haiku-5-5"

TASK_MODEL = {
    "normalize": MODEL_HAIKU,          # pull fields out of a free-text announcement
    "explain_identity": MODEL_SONNET,  # explain a code-computed identity score
    "history_summary": MODEL_SONNET,   # summarize the person's history with Cairnboard
    "draft_outreach": MODEL_SONNET,    # draft the outreach message
}

# Identity scoring (points, see agent/identity.py)
CONFIRM_THRESHOLD = 6.0   # at or above: same person, auto-confirmed
REVIEW_THRESHOLD = 3.5    # between review and confirm: a human settles it, no play fires
AMBIGUITY_MARGIN = 1.0    # two candidates this close, both above review: human settles it

DEDUPE_WINDOW_DAYS = 45
WATCH_ROLES = {"champion", "exec_sponsor"}
ROLE_LABEL = {"champion": "champion", "exec_sponsor": "executive sponsor"}

# Risk level from days until renewal
RISK_HIGH_DAYS = 120
RISK_MEDIUM_DAYS = 240

PRODUCT = "Cairnboard"
