"""Approval queue and a MOCK outbox.

The only way a message can reach the outbox is `ApprovalQueue.act()` with a named human reviewer.
The pipeline can create items (always `pending`) but has no path to `sent`. Nothing real is ever
sent: the outbox is an in-memory list.
"""
from __future__ import annotations

from datetime import datetime, timezone


class Outbox:
    """Mock outbox. `send` refuses anything that has not been approved or edited by a named human."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send(self, item: dict) -> None:
        if item.get("status") not in ("approved", "edited") or not item.get("reviewer"):
            raise PermissionError("outbox refuses items without a human approval")
        self.sent.append({"item_id": item["id"], "subject": item.get("subject"), "body": item.get("body"),
                          "approved_by": item["reviewer"], "mock": True})


class ApprovalQueue:
    def __init__(self, items: list[dict], outbox: Outbox | None = None):
        self.items = {i["id"]: i for i in items}
        self.outbox = outbox or Outbox()

    def act(self, item_id: str, action: str, reviewer: str, edited_body: str | None = None) -> dict:
        item = self.items[item_id]
        if item["type"] != "outreach_draft":
            raise ValueError("only outreach drafts can be approved, edited or rejected here")
        if item["status"] != "pending":
            raise ValueError(f"item is already {item['status']}")
        if not reviewer:
            raise PermissionError("a named reviewer is required")
        if action == "reject":
            item.update(status="rejected", reviewer=reviewer)
            return item
        if item["verification"]["ok"] is False and action == "approve":
            raise PermissionError("a draft that failed fact-checking cannot be approved as written; edit it")
        if action == "edit":
            if not edited_body:
                raise ValueError("edit needs the edited body")
            item.update(status="edited", reviewer=reviewer, body=edited_body)
        elif action == "approve":
            item.update(status="approved", reviewer=reviewer)
        else:
            raise ValueError(f"unknown action {action}")
        item["acted_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.outbox.send(item)
        item["status"] = "sent_mock"
        return item
