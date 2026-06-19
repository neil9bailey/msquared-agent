from msquared_agent.intake_store import add_intake_item, get_intake_item
from msquared_agent.intake_triage import triage_all_intake
from msquared_agent.interactive_agent import ask_agent, summarize_context
from msquared_agent.monitor_intelligence import build_monitor_intelligence_snapshot, format_monitor_intelligence


def test_monitor_intelligence_snapshot_includes_waiting_replies_and_noise():
    reply = add_intake_item({
        "channel": "x",
        "source_type": "x_mention",
        "source_id": "tweet-monitor-1",
        "author": "@buyer",
        "text": "Can MSquared explain how M2 evaluates governed AI decisions?",
    })
    add_intake_item({
        "channel": "x",
        "source_type": "x_monitor",
        "source_id": "tweet-monitor-2",
        "author": "123",
        "text": "Free followers casino giveaway promotion",
    })
    triage_all_intake(auto_archive=False)

    snapshot = build_monitor_intelligence_snapshot()
    text = format_monitor_intelligence(snapshot)

    assert snapshot["counts"]["waiting_reply"] == 1
    assert snapshot["counts"]["archive_candidates"] == 1
    assert snapshot["waiting_replies"][0]["canonical_id"] == reply["canonical_id"]
    assert "Waiting replies" in text
    assert reply["canonical_id"] in text


def test_agent_can_answer_using_monitor_intelligence_context():
    reply = add_intake_item({
        "channel": "email",
        "source_type": "website_contact",
        "source_id": "mail-monitor-1",
        "from": "prospect@example.com",
        "subject": "DIIaC and M2",
        "text": "Please send more information about DIIaC and M2 for enterprise AI governance.",
    })
    triage_all_intake(auto_archive=False)
    updated = get_intake_item(reply["id"])
    snapshot = build_monitor_intelligence_snapshot()

    answer = ask_agent("What is waiting in the monitor feed?", {"monitor_intelligence": snapshot})
    summary = summarize_context({"selected": {"kind": "intake", "item": updated}, "monitor_intelligence": snapshot})

    assert "Monitor intelligence" in answer["answer"]
    assert updated["canonical_id"] in answer["answer"]
    assert "monitor=" in summary
