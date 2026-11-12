from agent.rules import RULES, decide


def test_rule_table_matches_the_charter():
    assert decide("fit_prospect")["new_company_play"] == "create_contact_and_draft_outreach"
    assert decide("fit_prospect")["old_account_play"] == "risk_flag_and_csm_task"
    assert decide("customer")["new_company_play"] == "notify_account_manager"
    assert decide("competitor")["new_company_play"] == "suppress_outreach"
    assert decide("nofit_prospect")["new_company_play"] == "log_only"
    assert decide("none")["new_company_play"] == "none"
    assert decide("same_company")["new_company_play"] == "update_record"
    assert decide("same_company")["old_account_play"] == "none"


def test_every_departure_gets_the_old_account_play():
    for kind, (rule, new, old, label, _) in RULES.items():
        if kind != "same_company":
            assert old == "risk_flag_and_csm_task", kind


def test_competitor_never_gets_outreach():
    assert "outreach" not in decide("competitor")["new_company_play"].replace("suppress_outreach", "")
