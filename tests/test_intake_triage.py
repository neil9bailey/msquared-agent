from msquared_agent.action_router import detect_action_for_intake
from msquared_agent.intake_store import add_intake_item, get_intake_item
from msquared_agent.intake_triage import intake_triage_status, triage_all_intake, waiting_reply_items


def test_x_product_mention_is_waiting_reply():
    item = add_intake_item({
        "channel": "x",
        "source_type": "x_mention",
        "source_id": "tweet-100",
        "author": "@buyer",
        "text": "How does DIIaC governance work with M2 evaluation?",
    })

    result = triage_all_intake()
    updated = get_intake_item(item["id"])

    assert result["waiting_reply_count"] == 1
    assert updated["status"] == "needs_reply"
    assert updated["triage"]["label"] == "needs_reply"
    assert updated["triage"]["product_match"] == "both"
    assert waiting_reply_items()[0]["id"] == item["id"]
    assert detect_action_for_intake(updated)["action_type"] == "x_reply"


def test_email_contact_is_waiting_reply_even_without_product_terms():
    item = add_intake_item({
        "channel": "email",
        "source_type": "website_contact",
        "source_id": "message-100",
        "from": "prospect@example.com",
        "subject": "Request for information",
        "text": "Please send more information about your solution and how to book a call.",
    })

    triage_all_intake()
    updated = get_intake_item(item["id"])

    assert updated["status"] == "needs_reply"
    assert updated["triage"]["waiting_reply"] is True
    assert updated["triage"]["recommended_action"] == "generate_reply"
    assert detect_action_for_intake(updated)["action_type"] == "email_response"


def test_relevant_x_search_is_not_waiting_reply():
    item = add_intake_item({
        "channel": "x",
        "source_type": "x_monitor",
        "source_id": "tweet-200",
        "author": "123",
        "text": "DIIaC and governed decision intelligence are useful framing for enterprise AI assurance.",
    })

    triage_all_intake()
    updated = get_intake_item(item["id"])

    assert updated["status"] == "no_reply_needed"
    assert updated["triage"]["label"] == "relevant_no_reply_needed"
    assert updated["triage"]["waiting_reply"] is False
    assert detect_action_for_intake(updated)["action_type"] == "x_post"


def test_ambiguous_x_mention_does_not_auto_become_waiting_reply():
    item = add_intake_item({
        "channel": "x",
        "source_type": "x_mention",
        "source_id": "tweet-250",
        "author": "@random",
        "text": "What do you think about this?",
    })

    triage_all_intake()
    updated = get_intake_item(item["id"])

    assert updated["status"] == "needs_review"
    assert updated["triage"]["label"] == "unknown_review"
    assert updated["triage"]["waiting_reply"] is False


def test_spam_or_unrelated_items_can_be_archived_locally():
    item = add_intake_item({
        "channel": "x",
        "source_type": "x_monitor",
        "source_id": "tweet-300",
        "author": "123",
        "text": "Crypto airdrop giveaway casino free followers click here https://a.example https://b.example https://c.example",
    })

    result = triage_all_intake(auto_archive=True, confidence_threshold=0.50)
    updated = get_intake_item(item["id"])

    assert result["auto_archived_count"] == 1
    assert updated["status"] == "archived"
    assert updated["triage"]["label"] == "spam"
    assert updated["triage"]["archived_by_agent"] is True
    assert detect_action_for_intake(updated)["action_type"] == "manual"


def test_triage_status_summarizes_waiting_and_archive_candidates():
    add_intake_item({
        "channel": "x",
        "source_type": "x_mention",
        "source_id": "tweet-400",
        "author": "@buyer",
        "text": "Can MSquared explain model evaluation for governed AI?",
    })
    add_intake_item({
        "channel": "x",
        "source_type": "x_monitor",
        "source_id": "tweet-401",
        "author": "123",
        "text": "Free followers giveaway casino promotion",
    })

    triage_all_intake(auto_archive=False)
    status = intake_triage_status()

    assert status["waiting_reply_count"] == 1
    assert status["local_archive_candidate_count"] == 1
    assert status["label_counts"]["needs_reply"] == 1
    assert status["label_counts"]["spam"] == 1
