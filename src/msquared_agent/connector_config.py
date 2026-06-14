from .env_loader import DEFAULT_OPENAI_MODEL, env_bool, get_env, load_env_file, mask_secret
from .settings import load_feature_flags


def _x_monitor_reference_type(value: str | None) -> str:
    if not value:
        return "blank"
    stripped = str(value).strip()
    if stripped.isdigit():
        return "numeric_user_id"
    if stripped.startswith("@") or stripped.replace("_", "").isalnum():
        return "handle"
    return "unknown"


def x_connector_config() -> dict:
    load_env_file()
    return {
        "client_id": get_env("X_CLIENT_ID"),
        "client_secret": get_env("X_CLIENT_SECRET"),
        "oauth2_access_token": get_env("X_OAUTH2_ACCESS_TOKEN"),
        "oauth2_refresh_token": get_env("X_OAUTH2_REFRESH_TOKEN"),
        "oauth2_access_token_expires_at": get_env("X_OAUTH2_ACCESS_TOKEN_EXPIRES_AT"),
        "oauth2_scope": get_env("X_OAUTH2_SCOPE"),
        "bearer_token": get_env("X_BEARER_TOKEN"),
        "api_key": get_env("X_API_KEY") or get_env("X_CONSUMER_KEY"),
        "api_secret": get_env("X_API_SECRET") or get_env("X_CONSUMER_SECRET"),
        "consumer_key": get_env("X_CONSUMER_KEY") or get_env("X_API_KEY"),
        "consumer_secret": get_env("X_CONSUMER_SECRET") or get_env("X_API_SECRET"),
        "access_token": get_env("X_ACCESS_TOKEN"),
        "access_token_secret": get_env("X_ACCESS_TOKEN_SECRET"),
        "allow_oauth1_posting_fallback": get_env("X_ALLOW_OAUTH1_POSTING_FALLBACK", "false"),
        "monitor_query": get_env("X_MONITOR_QUERY", "DIIaC OR MSquared OR governed decision intelligence"),
        "monitor_user_id": get_env("X_MONITOR_USER_ID"),
        "app_permissions": get_env("X_APP_PERMISSIONS", "Read and write"),
        "app_type": get_env("X_APP_TYPE", "Web App, Automated App or Bot"),
        "callback_uri": get_env("X_CALLBACK_URI"),
        "website_url": get_env("X_WEBSITE_URL"),
        "organization_name": get_env("X_ORGANIZATION_NAME"),
        "organization_url": get_env("X_ORGANIZATION_URL"),
        "terms_url": get_env("X_TERMS_URL"),
        "privacy_url": get_env("X_PRIVACY_URL"),
        "request_email_from_users": get_env("X_REQUEST_EMAIL_FROM_USERS", "false"),
    }


def email_connector_config() -> dict:
    load_env_file()
    return {
        "imap_server": get_env("EMAIL_IMAP_SERVER"),
        "imap_port": get_env("EMAIL_IMAP_PORT", "993"),
        "imap_security": get_env("EMAIL_IMAP_SECURITY", "SSL/TLS"),
        "smtp_server": get_env("EMAIL_SMTP_SERVER"),
        "smtp_port": get_env("EMAIL_SMTP_PORT", "587"),
        "smtp_security": get_env("EMAIL_SMTP_SECURITY", "STARTTLS"),
        "pop_server": get_env("EMAIL_POP_SERVER", "pop.porkbun.com"),
        "pop_port": get_env("EMAIL_POP_PORT", "995"),
        "pop_security": get_env("EMAIL_POP_SECURITY", "SSL/TLS"),
        "webmail_url": get_env("EMAIL_WEBMAIL_URL", "https://webmail.porkbun.com/"),
        "email": get_env("EMAIL_ADDRESS"),
        "password": get_env("EMAIL_PASSWORD"),
        "mailbox": get_env("EMAIL_MAILBOX", "inbox"),
    }


def ai_agent_config() -> dict:
    load_env_file()
    return {
        "api_key": get_env("OPENAI_API_KEY"),
        "model": get_env("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL,
        "technical_openai_allowed": env_bool("ALLOW_OPENAI_TECHNICAL_CONTEXT", False),
        "knowledge_roots": get_env("PRODUCT_KNOWLEDGE_ROOTS"),
    }


def connector_status() -> dict:
    flags = load_feature_flags()
    x_config = x_connector_config()
    email_config = email_connector_config()
    ai_config = ai_agent_config()
    x_write_keys = ["api_key", "api_secret", "access_token", "access_token_secret"]
    oauth2_user_configured = bool(x_config["oauth2_access_token"] or x_config["oauth2_refresh_token"])
    oauth1a_user_configured = all(bool(x_config[key]) for key in x_write_keys)
    oauth1a_fallback_allowed = env_bool("X_ALLOW_OAUTH1_POSTING_FALLBACK", False)
    x_ready_to_write = bool(flags.get("ENABLE_X_WRITE") and (oauth2_user_configured or (oauth1a_user_configured and oauth1a_fallback_allowed)))
    if oauth2_user_configured:
        write_auth_mode = "oauth2_user"
        write_setup_warning = ""
    elif oauth1a_user_configured and oauth1a_fallback_allowed:
        write_auth_mode = "oauth1a_user"
        write_setup_warning = "OAuth 1.0a posting fallback is enabled; X may still reject /2/tweets if the access token was not regenerated after Read and write permissions."
    elif oauth1a_user_configured:
        write_auth_mode = "oauth1a_user_unverified"
        write_setup_warning = "OAuth 1.0a credentials are present, but OAuth 2.0 user-context tokens are recommended and required by default for /2/tweets posting."
    else:
        write_auth_mode = "missing"
        write_setup_warning = "X write is missing OAuth 2.0 user-context access and refresh tokens."
    email_read_keys = ["imap_server", "imap_port", "imap_security", "email", "password"]
    email_send_keys = ["smtp_server", "smtp_port", "smtp_security", "email", "password"]

    return {
        "x": {
            "read_enabled": bool(flags.get("ENABLE_X_READ")),
            "write_enabled": bool(flags.get("ENABLE_X_WRITE")),
            "client_id_configured": bool(x_config["client_id"]),
            "client_secret_configured": bool(x_config["client_secret"]),
            "oauth2_access_token_configured": bool(x_config["oauth2_access_token"]),
            "oauth2_refresh_token_configured": bool(x_config["oauth2_refresh_token"]),
            "oauth2_access_token_expires_at": x_config["oauth2_access_token_expires_at"] or "",
            "oauth2_scope_configured": bool(x_config["oauth2_scope"]),
            "bearer_token_configured": bool(x_config["bearer_token"]),
            "write_credentials_configured": bool(oauth2_user_configured or oauth1a_user_configured),
            "oauth1a_credentials_configured": bool(oauth1a_user_configured),
            "oauth1a_posting_fallback_allowed": bool(oauth1a_fallback_allowed),
            "write_auth_mode": write_auth_mode,
            "write_setup_warning": write_setup_warning,
            "monitor_query": x_config["monitor_query"],
            "monitor_user_id": x_config["monitor_user_id"] or "",
            "monitor_user_reference_type": _x_monitor_reference_type(x_config["monitor_user_id"]),
            "app_permissions": x_config["app_permissions"],
            "app_type": x_config["app_type"],
            "callback_uri_configured": bool(x_config["callback_uri"]),
            "website_url_configured": bool(x_config["website_url"]),
            "terms_url_configured": bool(x_config["terms_url"]),
            "privacy_url_configured": bool(x_config["privacy_url"]),
            "ready_to_read": bool(flags.get("ENABLE_X_READ") and (x_config["oauth2_access_token"] or x_config["oauth2_refresh_token"] or x_config["bearer_token"])),
            "ready_to_write": x_ready_to_write,
            "masked_client_id": mask_secret(x_config["client_id"]),
            "masked_oauth2_access_token": mask_secret(x_config["oauth2_access_token"]),
            "masked_oauth2_refresh_token": mask_secret(x_config["oauth2_refresh_token"]),
            "masked_bearer_token": mask_secret(x_config["bearer_token"]),
        },
        "email": {
            "read_enabled": bool(flags.get("ENABLE_EMAIL_READ")),
            "send_enabled": bool(flags.get("ENABLE_EMAIL_SEND")),
            "address": email_config["email"] or "",
            "imap_server": email_config["imap_server"] or "",
            "imap_port": email_config["imap_port"],
            "imap_security": email_config["imap_security"],
            "smtp_server": email_config["smtp_server"] or "",
            "smtp_port": email_config["smtp_port"],
            "smtp_security": email_config["smtp_security"],
            "pop_server": email_config["pop_server"] or "",
            "pop_port": email_config["pop_port"],
            "pop_security": email_config["pop_security"],
            "webmail_url": email_config["webmail_url"],
            "imap_configured": all(bool(email_config[key]) for key in email_read_keys),
            "smtp_configured": all(bool(email_config[key]) for key in email_send_keys),
            "ready_to_read": bool(flags.get("ENABLE_EMAIL_READ") and all(bool(email_config[key]) for key in email_read_keys)),
            "ready_to_send": bool(flags.get("ENABLE_EMAIL_SEND") and all(bool(email_config[key]) for key in email_send_keys)),
            "mailbox": email_config["mailbox"],
        },
        "ai_agent": {
            "openai_configured": bool(ai_config["api_key"]),
            "ready_to_answer": bool(ai_config["api_key"]),
            "model": ai_config["model"],
            "default_model": DEFAULT_OPENAI_MODEL,
            "technical_openai_allowed": bool(ai_config["technical_openai_allowed"]),
            "knowledge_roots_configured": bool(ai_config["knowledge_roots"]),
            "masked_api_key": mask_secret(ai_config["api_key"]),
        },
        "safety": {
            "human_approval_required": bool(flags.get("REQUIRE_HUMAN_APPROVAL")),
            "keyword_search_auto_reply_allowed": bool(flags.get("ALLOW_KEYWORD_SEARCH_AUTO_REPLY")),
            "unsolicited_dm_allowed": bool(flags.get("ALLOW_UNSOLICITED_DM")),
            "metadata_only_learning": bool(flags.get("METADATA_ONLY_LEARNING")),
        },
    }
