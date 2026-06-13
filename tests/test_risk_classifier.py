import pytest

from msquared_agent.agent import generate_draft
from msquared_agent.approval_queue import approve_item
from msquared_agent.risk_classifier import classify_action


def test_keyword_search_auto_reply_is_blocked():
    item = generate_draft(
        "x_reply",
        "",
        {"source": {"source_type": "keyword_search", "source_id": "tweet_1", "text": "What is DIIaC?"}},
    )
    assert item["risk_level"] == "block"
    with pytest.raises(ValueError):
        approve_item(item["id"])


def test_unsolicited_dm_action_is_blocked():
    risk = classify_action("x", "x_dm", "Hello from MSquared", {})
    assert risk["level"] == "block"
    assert "unsolicited_dm_blocked" in risk["reasons"]
