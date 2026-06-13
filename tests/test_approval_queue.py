from msquared_agent.agent import generate_draft
import pytest

from msquared_agent.approval_queue import approve_item, list_queue, mark_sent_or_posted, reject_item


def test_approval_queue_tracks_states_and_approver():
    item = generate_draft("x_post", "MSquared reviews governed decision artefacts.")
    approved = approve_item(item["id"], approver="Neil")
    assert approved["status"] == "approved"
    assert approved["approved_by"] == "Neil"

    queued = list_queue()
    assert queued[0]["id"] == item["id"]


def test_reject_item_sets_rejected_state():
    item = generate_draft("x_post", "Useful before promotional.")
    rejected = reject_item(item["id"])
    assert rejected["status"] == "rejected"


def test_approval_queue_rejects_invalid_state_transitions():
    item = generate_draft("x_post", "A governed decision needs evidence and human review.")
    approve_item(item["id"])

    with pytest.raises(ValueError):
        reject_item(item["id"])

    mark_sent_or_posted(item["id"])
    with pytest.raises(ValueError):
        approve_item(item["id"])


def test_blocked_item_can_be_rejected_but_not_approved():
    item = generate_draft("x_post", "DIIaC guarantees compliance for every decision.")

    with pytest.raises(ValueError):
        approve_item(item["id"])

    rejected = reject_item(item["id"], reason="Forbidden compliance claim.")
    assert rejected["status"] == "rejected"
    assert rejected["rejection_reason"] == "Forbidden compliance claim."
