from msquared_agent.agent import generate_draft
from msquared_agent.approval_queue import approve_item
from msquared_agent.email_adapter import send_approved_email
from msquared_agent.x_adapter import post_approved_tweet

def test_no_auto_post():
    item = generate_draft("x_post", "Test post")
    assert item["status"] == "drafted"  # Phase 0 only drafts
    approve_item(item["id"])
    result = post_approved_tweet(item["id"], {})
    assert result["sent"] is False
    assert result["reason"] == "ENABLE_X_WRITE=false"


def test_no_auto_send_email():
    item = generate_draft(
        "email_response",
        "",
        {"source": {"from": "lead@example.com", "subject": "Demo request", "text": "Can I book a demo?", "source_type": "website_contact"}},
    )
    approve_item(item["id"])
    result = send_approved_email(item["id"], {})
    assert result["sent"] is False
    assert result["reason"] == "ENABLE_EMAIL_SEND=false"
