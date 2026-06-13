from msquared_agent.app_log import log_event, read_log_events
from msquared_agent.email_adapter import fetch_inbound_emails
from msquared_agent.settings import save_feature_flags
from msquared_agent.x_adapter import fetch_x_feed


def test_app_log_redacts_secrets_and_omits_content(monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "very-secret-token")

    entry = log_event(
        "diagnostic_test",
        "error",
        "Bearer very-secret-token failed for neil@example.com",
        {
            "access_token": "very-secret-token",
            "text": "private customer message",
            "body": "private email body",
        },
    )

    rendered = str(entry)
    assert "very-secret-token" not in rendered
    assert "private customer message" not in rendered
    assert "private email body" not in rendered
    assert "[REDACTED]" in rendered
    assert "[CONTENT_OMITTED]" in rendered

    persisted = str(read_log_events())
    assert "very-secret-token" not in persisted
    assert "private customer message" not in persisted


def test_x_read_missing_bearer_token_is_visible_in_app_log(monkeypatch):
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    save_feature_flags({"ENABLE_X_READ": True})

    items = fetch_x_feed({})

    assert items == []
    events = read_log_events()
    assert any(event["event"] == "x_fetch_skipped" and event["level"] == "warning" for event in events)


def test_email_read_missing_credentials_is_visible_in_app_log(monkeypatch):
    for key in ("EMAIL_IMAP_SERVER", "EMAIL_ADDRESS", "EMAIL_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    save_feature_flags({"ENABLE_EMAIL_READ": True})

    items = fetch_inbound_emails({})

    assert items == []
    events = read_log_events()
    assert any(event["event"] == "email_fetch_skipped" and event["level"] == "warning" for event in events)
