import pytest

from msquared_agent.agent import generate_draft
from msquared_agent.approval_queue import approve_item
from msquared_agent.audit_store import read_audit_records
from msquared_agent.email_adapter import prepare_email_payload
from msquared_agent.opt_out_registry import add_opt_out
from msquared_agent.x_adapter import prepare_x_payload


def test_approved_original_post_can_prepare_x_payload_without_sending():
    item = generate_draft("x_post", "A governed decision needs evidence and human review.")
    approve_item(item["id"])
    payload = prepare_x_payload(item["id"])
    assert payload["endpoint"] == "/2/tweets"
    assert payload["json"]["text"]
    assert payload["metadata"]["made_with_ai"] is True


def test_approved_email_can_prepare_payload_without_sending():
    item = generate_draft(
        "email_response",
        "",
        {"source": {"from": "buyer@example.com", "subject": "Pricing", "text": "Can you send pricing?", "source_type": "website_contact"}},
    )
    approve_item(item["id"])
    payload = prepare_email_payload(item["id"])
    assert payload["to"] == "buyer@example.com"
    assert payload["subject"].startswith("Re:")
    assert payload["body"]


def test_opt_out_prevents_outbound_email_payload():
    add_opt_out("buyer@example.com", "email", "requested no automation")
    item = generate_draft(
        "email_response",
        "",
        {"source": {"from": "buyer@example.com", "subject": "Demo", "text": "Can I get a demo?", "source_type": "website_contact"}},
    )
    approve_item(item["id"])
    with pytest.raises(PermissionError):
        prepare_email_payload(item["id"])


def test_audit_record_created_for_draft_and_approval():
    item = generate_draft("x_post", "Review signal, not approval signal.")
    approve_item(item["id"])
    records = read_audit_records()
    actions = [record["action"] for record in records]
    assert "draft_generated" in actions
    assert "approval_granted" in actions
