from agent.company import CompanyIndex
from agent.identity import IdentityResolver

ACCTS = [{"id": "A1", "name": "Lumenforge", "domain": "lumenforge.example"},
         {"id": "A2", "name": "Cobaltgrid", "domain": "cobaltgrid.example"}]
CONTACTS = [
    {"id": "K1", "account_id": "A1", "first_name": "Katherine", "last_name": "Ramos", "full_name": "Katherine Ramos",
     "title": "Senior Product Manager", "city": "Austin", "role": "champion"},
    {"id": "K2", "account_id": "A2", "first_name": "Katherine", "last_name": "Thorne", "full_name": "Katherine Thorne",
     "title": "Product Manager", "city": "Denver", "role": "champion"},
]


def resolver():
    idx = CompanyIndex(ACCTS, [], [])
    return IdentityResolver(CONTACTS, ACCTS, idx)


def ev(**kw):
    base = dict(full_name="Katherine Ramos", prior_employer=None, prior_title=None, prior_email_domain=None,
                new_employer=None, new_title=None, location=None)
    return {**base, **kw}


def test_exact_name_and_employer_confirms():
    r = resolver().resolve(ev(prior_employer="Lumenforge Inc."))
    assert r["status"] == "confirmed" and r["contact_id"] == "K1" and r["rule"] == "I1"


def test_nickname_with_employer_and_title_confirms():
    r = resolver().resolve(ev(full_name="Kate Ramos", prior_employer="lumenforge",
                              prior_title="Sr Product Manager"))
    assert r["status"] == "confirmed"


def test_same_name_different_employer_is_not_a_match():
    r = resolver().resolve(ev(prior_employer="Cobaltgrid", location="Austin"))
    # the exact-name contact is at Lumenforge; the employer says Cobaltgrid
    assert r["status"] in ("no_match", "review") and r["status"] != "confirmed"


def test_sparse_event_is_held_for_review_not_confirmed():
    r = resolver().resolve(ev(location="Austin", prior_title="Senior Product Manager"))
    assert r["status"] == "review" and r["rule"] == "G3"


def test_surname_mismatch_alone_cannot_confirm():
    # same first name, same employer, similar title, same city, different surname: a colleague, not a match
    r = resolver().resolve(ev(full_name="Katherine Bergstrom", prior_employer="Cobaltgrid",
                              prior_title="Product Manager", location="Denver"))
    assert r["status"] != "confirmed"


def test_surname_change_with_matching_email_domain_confirms():
    r = resolver().resolve(ev(full_name="Katherine Okafor", prior_employer="Lumenforge",
                              prior_email_domain="lumenforge.example"))
    assert r["status"] == "confirmed" and r["contact_id"] == "K1"


def test_unknown_name_has_no_candidates():
    r = resolver().resolve(ev(full_name="Zed Nobody"))
    assert r["status"] == "no_match" and r["contact_id"] is None
