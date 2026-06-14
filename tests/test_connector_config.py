import os
from pathlib import Path

from msquared_agent.connector_config import connector_status
from msquared_agent.env_loader import load_env_file, read_env_values, save_env_values
from msquared_agent.settings import load_feature_flags, save_feature_flags


def test_env_file_loads_from_portable_app_home(monkeypatch):
    app_home = Path(os.environ["MSQUARED_AGENT_HOME"])
    env_file = app_home / ".env"
    env_file.write_text(
        "\n".join(
            [
                "ENABLE_X_READ=true",
                "X_CLIENT_ID=client-id-secretish",
                "X_CLIENT_SECRET=client-secret",
                "X_OAUTH2_ACCESS_TOKEN=oauth2-access-secret",
                "X_OAUTH2_REFRESH_TOKEN=oauth2-refresh-secret",
                "X_CONSUMER_KEY=consumer-key",
                "X_CONSUMER_SECRET=consumer-secret",
                "X_MONITOR_QUERY=\"DIIaC OR MSquared\"",
                "X_APP_PERMISSIONS=\"Read and write\"",
                "X_APP_TYPE=\"Web App, Automated App or Bot\"",
                "ENABLE_EMAIL_READ=true",
                "EMAIL_IMAP_SERVER=imap.example.com",
                "EMAIL_IMAP_PORT=993",
                "EMAIL_IMAP_SECURITY=SSL/TLS",
                "EMAIL_SMTP_SERVER=smtp.example.com",
                "EMAIL_SMTP_PORT=587",
                "EMAIL_SMTP_SECURITY=STARTTLS",
                "EMAIL_POP_SERVER=pop.example.com",
                "EMAIL_POP_PORT=995",
                "EMAIL_POP_SECURITY=SSL/TLS",
                "EMAIL_WEBMAIL_URL=https://webmail.example.com/",
                "EMAIL_ADDRESS=msquared@example.com",
                "EMAIL_PASSWORD=email-secret",
                "OPENAI_API_KEY=sk-openai-secret",
                "OPENAI_MODEL=gpt-example",
                "PRODUCT_KNOWLEDGE_ROOTS=F:\\code\\diiac",
                "ALLOW_OPENAI_TECHNICAL_CONTEXT=true",
            ]
        ),
        encoding="utf-8",
    )

    for key in [
        "ENABLE_X_READ",
        "X_CLIENT_ID",
        "X_CLIENT_SECRET",
        "X_OAUTH2_ACCESS_TOKEN",
        "X_OAUTH2_REFRESH_TOKEN",
        "X_CONSUMER_KEY",
        "X_CONSUMER_SECRET",
        "X_MONITOR_QUERY",
        "X_MONITOR_USER_ID",
        "X_APP_PERMISSIONS",
        "X_APP_TYPE",
        "ENABLE_EMAIL_READ",
        "EMAIL_IMAP_SERVER",
        "EMAIL_IMAP_PORT",
        "EMAIL_IMAP_SECURITY",
        "EMAIL_SMTP_SERVER",
        "EMAIL_SMTP_PORT",
        "EMAIL_SMTP_SECURITY",
        "EMAIL_POP_SERVER",
        "EMAIL_POP_PORT",
        "EMAIL_POP_SECURITY",
        "EMAIL_WEBMAIL_URL",
        "EMAIL_ADDRESS",
        "EMAIL_PASSWORD",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "PRODUCT_KNOWLEDGE_ROOTS",
        "ALLOW_OPENAI_TECHNICAL_CONTEXT",
    ]:
        monkeypatch.delenv(key, raising=False)

    loaded = load_env_file(override=True)
    status = connector_status()

    assert env_file.resolve() in [path.resolve() for path in loaded]
    assert status["x"]["ready_to_read"] is True
    assert status["x"]["client_id_configured"] is True
    assert status["x"]["client_secret_configured"] is True
    assert status["x"]["oauth2_access_token_configured"] is True
    assert status["x"]["oauth2_refresh_token_configured"] is True
    assert status["x"]["write_auth_mode"] == "oauth2_user"
    assert status["x"]["app_permissions"] == "Read and write"
    assert status["x"]["monitor_user_reference_type"] == "blank"
    assert status["email"]["ready_to_read"] is True
    assert status["email"]["imap_port"] == "993"
    assert status["email"]["imap_security"] == "SSL/TLS"
    assert status["email"]["smtp_port"] == "587"
    assert status["email"]["smtp_security"] == "STARTTLS"
    assert status["email"]["pop_server"] == "pop.example.com"
    assert status["email"]["webmail_url"] == "https://webmail.example.com/"
    assert status["ai_agent"]["openai_configured"] is True
    assert status["ai_agent"]["ready_to_answer"] is True
    assert status["ai_agent"]["model"] == "gpt-example"
    assert status["ai_agent"]["technical_openai_allowed"] is True
    assert status["ai_agent"]["knowledge_roots_configured"] is True
    assert status["ai_agent"]["masked_api_key"] == "sk-***ret"
    assert status["x"]["masked_oauth2_access_token"] == "oau***ret"
    assert "oauth2-access-secret" not in str(status)
    assert "oauth2-refresh-secret" not in str(status)
    assert "client-secret" not in str(status)
    assert "consumer-secret" not in str(status)
    assert "email-secret" not in str(status)
    assert "sk-openai-secret" not in str(status)


def test_admin_settings_persist_credentials_and_feature_flags(monkeypatch):
    app_home = Path(os.environ["MSQUARED_AGENT_HOME"])
    for key in [
        "ENABLE_X_READ",
        "ENABLE_X_WRITE",
        "X_CLIENT_ID",
        "X_CLIENT_SECRET",
        "X_OAUTH2_ACCESS_TOKEN",
        "X_OAUTH2_REFRESH_TOKEN",
        "X_BEARER_TOKEN",
        "X_CONSUMER_KEY",
        "X_CONSUMER_SECRET",
        "X_MONITOR_USER_ID",
        "X_APP_PERMISSIONS",
        "X_APP_TYPE",
        "EMAIL_IMAP_SERVER",
        "EMAIL_IMAP_PORT",
        "EMAIL_IMAP_SECURITY",
        "EMAIL_SMTP_SERVER",
        "EMAIL_SMTP_PORT",
        "EMAIL_SMTP_SECURITY",
        "EMAIL_POP_SERVER",
        "EMAIL_POP_PORT",
        "EMAIL_POP_SECURITY",
        "EMAIL_WEBMAIL_URL",
        "EMAIL_ADDRESS",
        "EMAIL_PASSWORD",
    ]:
        monkeypatch.delenv(key, raising=False)

    saved_flags = save_feature_flags({
        "ENABLE_X_READ": True,
        "ENABLE_X_WRITE": False,
        "ENABLE_EMAIL_READ": True,
        "ENABLE_EMAIL_SEND": False,
        "REQUIRE_HUMAN_APPROVAL": True,
        "ALLOW_KEYWORD_SEARCH_AUTO_REPLY": False,
        "ALLOW_UNSOLICITED_DM": False,
        "METADATA_ONLY_LEARNING": True,
    })
    save_env_values({
        "X_CLIENT_ID": "oauth2-client-id",
        "X_CLIENT_SECRET": "oauth2-client-secret",
        "X_OAUTH2_ACCESS_TOKEN": "oauth2-access-token",
        "X_OAUTH2_REFRESH_TOKEN": "oauth2-refresh-token",
        "X_BEARER_TOKEN": "token-123",
        "X_CONSUMER_KEY": "consumer-key",
        "X_CONSUMER_SECRET": "consumer-secret",
        "X_MONITOR_USER_ID": "123456",
        "X_APP_PERMISSIONS": "Read and write",
        "X_APP_TYPE": "Web App, Automated App or Bot",
        "EMAIL_IMAP_SERVER": "imap.example.com",
        "EMAIL_IMAP_PORT": "993",
        "EMAIL_IMAP_SECURITY": "SSL/TLS",
        "EMAIL_SMTP_SERVER": "smtp.example.com",
        "EMAIL_SMTP_PORT": "50587",
        "EMAIL_SMTP_SECURITY": "STARTTLS Alt.",
        "EMAIL_POP_SERVER": "pop.example.com",
        "EMAIL_POP_PORT": "995",
        "EMAIL_POP_SECURITY": "SSL/TLS",
        "EMAIL_WEBMAIL_URL": "https://webmail.example.com/",
        "EMAIL_ADDRESS": "msquared@example.com",
        "EMAIL_PASSWORD": "mail-secret",
        **{key: "true" if value else "false" for key, value in saved_flags.items()},
    })

    for key in [
        "ENABLE_X_READ",
        "ENABLE_EMAIL_READ",
        "X_CLIENT_ID",
        "X_CLIENT_SECRET",
        "X_OAUTH2_ACCESS_TOKEN",
        "X_OAUTH2_REFRESH_TOKEN",
        "X_BEARER_TOKEN",
        "X_CONSUMER_KEY",
        "X_CONSUMER_SECRET",
        "X_MONITOR_USER_ID",
        "EMAIL_IMAP_SERVER",
        "EMAIL_IMAP_PORT",
        "EMAIL_IMAP_SECURITY",
        "EMAIL_SMTP_SERVER",
        "EMAIL_SMTP_PORT",
        "EMAIL_SMTP_SECURITY",
        "EMAIL_POP_SERVER",
        "EMAIL_POP_PORT",
        "EMAIL_POP_SECURITY",
        "EMAIL_WEBMAIL_URL",
        "EMAIL_ADDRESS",
        "EMAIL_PASSWORD",
    ]:
        monkeypatch.delenv(key, raising=False)

    load_env_file(override=True)
    env_values = read_env_values()
    flags = load_feature_flags()
    status = connector_status()

    assert (app_home / ".env").exists()
    assert (app_home / "config" / "feature_flags.yaml").exists()
    assert env_values["X_CLIENT_ID"] == "oauth2-client-id"
    assert env_values["X_OAUTH2_ACCESS_TOKEN"] == "oauth2-access-token"
    assert env_values["X_OAUTH2_REFRESH_TOKEN"] == "oauth2-refresh-token"
    assert env_values["X_CONSUMER_KEY"] == "consumer-key"
    assert env_values["X_MONITOR_USER_ID"] == "123456"
    assert status["x"]["monitor_user_reference_type"] == "numeric_user_id"
    assert flags["ENABLE_X_READ"] is True
    assert flags["ENABLE_EMAIL_READ"] is True
    assert status["x"]["ready_to_read"] is True
    assert status["x"]["write_auth_mode"] == "oauth2_user"
    assert status["email"]["ready_to_read"] is True
    assert status["email"]["imap_server"] == "imap.example.com"
    assert status["email"]["imap_port"] == "993"
    assert status["email"]["imap_security"] == "SSL/TLS"
    assert status["email"]["smtp_server"] == "smtp.example.com"
    assert status["email"]["smtp_port"] == "50587"
    assert status["email"]["smtp_security"] == "STARTTLS Alt."
    assert status["email"]["pop_server"] == "pop.example.com"
    assert status["email"]["pop_port"] == "995"
    assert status["email"]["webmail_url"] == "https://webmail.example.com/"
    assert "token-123" not in str(status)
    assert "oauth2-access-token" not in str(status)
    assert "oauth2-refresh-token" not in str(status)
    assert "oauth2-client-secret" not in str(status)
    assert "consumer-secret" not in str(status)
    assert "mail-secret" not in str(status)


def test_x_oauth1_only_is_unverified_for_posting_by_default():
    save_feature_flags({"ENABLE_X_WRITE": True})
    save_env_values({
        "X_CONSUMER_KEY": "consumer-key",
        "X_CONSUMER_SECRET": "consumer-secret",
        "X_API_KEY": "consumer-key",
        "X_API_SECRET": "consumer-secret",
        "X_ACCESS_TOKEN": "access-token",
        "X_ACCESS_TOKEN_SECRET": "access-token-secret",
        "X_ALLOW_OAUTH1_POSTING_FALLBACK": "false",
    })

    status = connector_status()

    assert status["x"]["write_credentials_configured"] is True
    assert status["x"]["oauth1a_credentials_configured"] is True
    assert status["x"]["write_auth_mode"] == "oauth1a_user_unverified"
    assert status["x"]["ready_to_write"] is False
    assert "OAuth 2.0 user-context" in status["x"]["write_setup_warning"]
