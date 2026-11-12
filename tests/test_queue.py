import pytest

from agent.queue import ApprovalQueue, Outbox


def item(i="Q1", ok=True, kind="outreach_draft"):
    return {"id": i, "type": kind, "status": "pending", "subject": "s", "body": "b",
            "verification": {"ok": ok, "problems": []}}


def test_outbox_refuses_unapproved_items():
    with pytest.raises(PermissionError):
        Outbox().send(item())


def test_outbox_refuses_approved_item_without_reviewer():
    it = item()
    it["status"] = "approved"
    with pytest.raises(PermissionError):
        Outbox().send(it)


def test_approval_needs_a_named_human():
    q = ApprovalQueue([item()])
    with pytest.raises(PermissionError):
        q.act("Q1", "approve", reviewer="")
    assert q.outbox.sent == []


def test_approve_sends_exactly_once_to_the_mock_outbox():
    q = ApprovalQueue([item()])
    q.act("Q1", "approve", reviewer="rep.demo")
    assert len(q.outbox.sent) == 1 and q.outbox.sent[0]["mock"] is True
    with pytest.raises(ValueError):
        q.act("Q1", "approve", reviewer="rep.demo")


def test_reject_sends_nothing():
    q = ApprovalQueue([item()])
    q.act("Q1", "reject", reviewer="rep.demo")
    assert q.outbox.sent == []


def test_edit_replaces_body_before_sending():
    q = ApprovalQueue([item()])
    q.act("Q1", "edit", reviewer="rep.demo", edited_body="new body")
    assert q.outbox.sent[0]["body"] == "new body"


def test_failed_draft_cannot_be_approved_as_written():
    q = ApprovalQueue([item(ok=False)])
    with pytest.raises(PermissionError):
        q.act("Q1", "approve", reviewer="rep.demo")


def test_only_outreach_drafts_can_be_actioned():
    q = ApprovalQueue([item(kind="identity_review")])
    with pytest.raises(ValueError):
        q.act("Q1", "approve", reviewer="rep.demo")
