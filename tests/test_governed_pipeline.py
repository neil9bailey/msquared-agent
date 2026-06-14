from msquared_agent.action_preflight import run_action_preflight
from msquared_agent.agent import generate_draft
from msquared_agent.approval_queue import approve_item, update_approval_item
from msquared_agent.env_loader import save_env_values
from msquared_agent.feedback_store import read_feedback, similar_approved_examples
from msquared_agent.intake_store import add_intake_item
from msquared_agent.legal_agent import review_approval_item
from msquared_agent.settings import save_feature_flags


def test_intake_assigns_canonical_ids_and_deduplicates_sources():
    first = add_intake_item({
        "channel": "x",
        "source_type": "x_mention",
        "source_id": "tweet-1",
        "author": "@someone",
        "text": "How does DIIaC governance work?",
    })
    duplicate = add_intake_item({
        "channel": "x",
        "source_type": "x_mention",
        "source_id": "tweet-1",
        "author": "@someone",
        "text": "Duplicate should not create a new item.",
    })
    email = add_intake_item({
        "channel": "email",
        "source_type": "website_contact",
        "source_id": "message-1",
        "from": "buyer@example.com",
        "subject": "DIIaC information",
        "text": "Please send more information.",
    })

    assert first["canonical_id"].startswith("MSQ-X-")
    assert duplicate["id"] == first["id"]
    assert email["canonical_id"].startswith("MSQ-EM-")


def test_draft_data_model_preserves_raw_final_and_source_ids():
    source = add_intake_item({
        "channel": "x",
        "source_type": "x_mention",
        "source_id": "tweet-42",
        "author": "@analyst",
        "text": "Can MSquared explain governed decision intelligence?",
    })

    item = generate_draft("x_reply", source["text"], {"source": source})

    assert item["source_intake_id"] == source["canonical_id"]
    assert item["external_source_id"] == "tweet-42"
    assert item["reply_to"] == "tweet-42"
    assert item["raw_agent_draft"] == item["final_draft"] == item["draft"]
    assert item["draft_versions"][0]["version"] == "raw_agent"


def test_legal_review_only_changes_clear_claim_boundary_issues():
    item = generate_draft("x_post", "DIIaC guarantees compliance for every decision.")

    reviewed = review_approval_item(item["id"])

    assert reviewed["legal_review"]["decision"] == "require_changes"
    assert reviewed["legal_review"]["changed"] is True
    assert reviewed["pipeline_state"] == "legal_recommended_changes"
    assert "supports evidence-bound governance review" in reviewed["final_draft"]


def test_preflight_blocks_unapproved_then_passes_approved_x_reply():
    save_feature_flags({"ENABLE_X_WRITE": True})
    save_env_values({
        "X_OAUTH2_ACCESS_TOKEN": "oauth2-user-token",
        "X_OAUTH2_REFRESH_TOKEN": "oauth2-refresh-token",
    })
    source = add_intake_item({
        "channel": "x",
        "source_type": "x_mention",
        "source_id": "tweet-99",
        "author": "@buyer",
        "text": "What is M2?",
    })
    item = generate_draft("x_reply", source["text"], {"source": source})

    blocked = run_action_preflight(item["id"])
    assert blocked["decision"] == "blocked"

    approve_item(item["id"])
    passed = run_action_preflight(item["id"])

    assert passed["decision"] == "pass"
    assert passed["action"] == "x_reply"
    assert passed["payload"]["json"]["reply"]["in_reply_to_tweet_id"] == "tweet-99"


def test_governed_feedback_records_approval_and_retrieves_similar_examples():
    item = generate_draft("x_post", "DIIaC helps teams review governed decision artefacts.")
    update_approval_item(item["id"], {"human_edits_delta": "- old\n+ improved"})

    approve_item(item["id"])

    rows = read_feedback()
    assert rows[-1]["draft_id"] == item["id"]
    assert rows[-1]["outcome"] == "approved"
    assert rows[-1]["human_edits_delta"] == "- old\n+ improved"

    examples = similar_approved_examples("governed decision artefacts", action_type="x_post")
    assert examples
    assert examples[0]["draft_id"] == item["id"]
