"""The rules table. Plain code, identical every run, owned by RevOps.

Destination kinds come from agent.company / pipeline.classify:
  fit_prospect, customer, competitor, nofit_prospect, unknown, none, same_company
"""
from __future__ import annotations

# kind -> (rule id, new-company play, old-account play, label, description)
RULES: dict[str, tuple[str, str, str, str, str]] = {
    "fit_prospect": ("R1", "create_contact_and_draft_outreach", "risk_flag_and_csm_task", "departure:fit_prospect",
                     "Moved to a company that fits and is not a customer"),
    "customer": ("R2", "notify_account_manager", "risk_flag_and_csm_task", "departure:customer",
                 "Moved to an existing customer"),
    "competitor": ("R3", "suppress_outreach", "risk_flag_and_csm_task", "departure:competitor",
                   "Moved to a competitor: outreach suppressed"),
    "nofit_prospect": ("R4", "log_only", "risk_flag_and_csm_task", "departure:nofit_prospect",
                       "Moved to a company that does not fit"),
    "none": ("R5", "none", "risk_flag_and_csm_task", "departure:no_new_employer", "No new employer known"),
    "same_company": ("R6", "update_record", "none", "same_company_title_change", "Same company, new title"),
    "unknown": ("R7", "log_only_flag_for_revops_review", "risk_flag_and_csm_task", "departure:unknown_company",
                "Moved to a company that is not in any list"),
}

# Guard rules, evaluated before the table above.
GUARDS = {
    "G1": "Duplicate of an earlier event: logged, no second task",
    "G2": "Identity score below the review threshold: not the same person, no action",
    "G3": "Identity score in the review band: a human settles it, no play fires",
    "G4": "Contact is not on the watch list (champions and executive sponsors only): logged, no play",
    "G5": "Event text could not be normalized and validated: sent to review, no play",
}


def decide(kind: str) -> dict:
    rule, new_play, old_play, label, desc = RULES[kind]
    return {"rule": rule, "new_company_play": new_play, "old_account_play": old_play, "label": label,
            "description": desc}
