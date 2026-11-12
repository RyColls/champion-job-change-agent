from agent.ai import TemplateBackend
from agent.verify import verify_draft, verify_text

FACTS = {"contact.first_name": "Kate", "contact.full_name": "Katherine Ramos", "contact.role_label": "champion",
         "contact.old_title": "Senior Product Manager", "contact.signup_date": "2024-03-02",
         "contact.last_active_date": "2026-07-14", "contact.boards_created": "41", "account.name": "Lumenforge",
         "account.plan": "Business", "account.usage_level": "high", "account.customer_since": "2023-05-11",
         "new_company.name": "Cobaltgrid", "new_title": "Head of Product"}


def draft():
    return TemplateBackend().call("draft_outreach", {"facts": FACTS})[0]


def test_clean_draft_passes():
    assert verify_draft(draft(), FACTS)["ok"]


def swap(body_suffix, **kw):
    d = draft()
    d["body"] = d["body"] + body_suffix
    return verify_draft(d, FACTS)


def test_invented_outcome_blocked():
    assert not swap("\n\nCairnboard helped your team cut onboarding time by 40%.")["ok"]


def test_invented_number_blocked():
    assert not swap(" We have 12 customers like yours.")["ok"]


def test_wrong_company_blocked():
    d = draft()
    d["body"] = d["body"].replace("Lumenforge", "Ironwoodgrid")
    assert not verify_draft(d, FACTS)["ok"]


def test_invented_person_blocked():
    assert not swap("\n\nSay hi to Hannah from us.")["ok"]


def test_invented_duration_blocked():
    assert not swap("\n\nYou were with us for three years.")["ok"]


def test_claim_pointing_at_wrong_value_blocked():
    d = draft()
    d["claims"][0] = {"text": "Katherine", "field": "contact.first_name"}
    assert not verify_draft(d, FACTS)["ok"]


def test_claim_pointing_at_unknown_field_blocked():
    d = draft()
    d["claims"].append({"text": "Lumenforge", "field": "account.revenue"})
    assert not verify_draft(d, FACTS)["ok"]


def test_summary_with_only_record_facts_passes():
    s = TemplateBackend().call("history_summary", {"facts": FACTS})[0]["summary"]
    assert verify_text(s, FACTS)["ok"]


def test_possessive_of_a_record_word_is_not_flagged():
    assert verify_text("The account is on the Business plan, and Kate's last activity was 2026-07-14.", FACTS)["ok"]
    assert not verify_text("Say hi to Hannah's team.", FACTS)["ok"]


def test_gendered_pronoun_blocked():
    assert not verify_text("Kate was our champion and she created 41 boards.", FACTS)["ok"]
