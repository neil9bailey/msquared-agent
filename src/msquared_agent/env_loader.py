import os
from pathlib import Path

from .paths import app_root, source_root

ALLOWED_OPENAI_MODELS = (
    "gpt-5-nano",
    "gpt-5-mini",
    "gpt-5",
    "gpt-5-pro",
    "gpt-5.5",
    "gpt-5.5-2026-04-23",
    "gpt-5.5-pro",
    "gpt-5.4-mini-2026-03-17",
    "gpt-5.4-nano-2026-03-17",
    "gpt-5.4-pro",
)
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini-2026-03-17"

ENV_KEYS = [
    "X_CLIENT_ID",
    "X_CLIENT_SECRET",
    "X_OAUTH2_ACCESS_TOKEN",
    "X_OAUTH2_REFRESH_TOKEN",
    "X_OAUTH2_ACCESS_TOKEN_EXPIRES_AT",
    "X_OAUTH2_SCOPE",
    "X_BEARER_TOKEN",
    "X_API_KEY",
    "X_API_SECRET",
    "X_CONSUMER_KEY",
    "X_CONSUMER_SECRET",
    "X_ACCESS_TOKEN",
    "X_ACCESS_TOKEN_SECRET",
    "X_ALLOW_OAUTH1_POSTING_FALLBACK",
    "X_MONITOR_USER_ID",
    "X_MONITOR_QUERY",
    "X_APP_PERMISSIONS",
    "X_APP_TYPE",
    "X_CALLBACK_URI",
    "X_WEBSITE_URL",
    "X_ORGANIZATION_NAME",
    "X_ORGANIZATION_URL",
    "X_TERMS_URL",
    "X_PRIVACY_URL",
    "X_REQUEST_EMAIL_FROM_USERS",
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
    "EMAIL_MAILBOX",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "PRODUCT_KNOWLEDGE_ROOTS",
    "ALLOW_OPENAI_TECHNICAL_CONTEXT",
    "ENABLE_X_READ",
    "ENABLE_X_WRITE",
    "ENABLE_EMAIL_READ",
    "ENABLE_EMAIL_SEND",
    "REQUIRE_HUMAN_APPROVAL",
    "ALLOW_KEYWORD_SEARCH_AUTO_REPLY",
    "ALLOW_UNSOLICITED_DM",
    "METADATA_ONLY_LEARNING",
    "ENABLE_AUTO_TRIAGE",
    "AUTO_ARCHIVE_HIGH_CONFIDENCE_SPAM",
    "AUTO_DRAFT_RELEVANT_REPLIES",
    "AUTO_TRIAGE_CONFIDENCE_THRESHOLD",
]


def _parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip().strip('"').strip("'")
    return key, value


def env_file_candidates() -> list[Path]:
    candidates = [app_root() / ".env", source_root() / ".env"]
    unique = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def load_env_file(override: bool = False) -> list[Path]:
    loaded = []
    for path in env_file_candidates():
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as file:
            for line in file:
                parsed = _parse_env_line(line)
                if not parsed:
                    continue
                key, value = parsed
                if override or key not in os.environ:
                    os.environ[key] = value
        loaded.append(path)
    return loaded


def read_env_values() -> dict:
    values = {}
    for path in reversed(env_file_candidates()):
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as file:
            for line in file:
                parsed = _parse_env_line(line)
                if parsed:
                    key, value = parsed
                    values[key] = value
    values.update({key: os.environ[key] for key in ENV_KEYS if key in os.environ})
    return values


def save_env_values(values: dict, env_path: Path | None = None) -> Path:
    path = env_path or app_root() / ".env"
    path.parent.mkdir(parents=True, exist_ok=True)

    current = read_env_values()
    current.update({key: "" if value is None else str(value) for key, value in values.items()})

    lines = [
        "# MSquared Agent local admin settings",
        "# Stored next to the portable exe. Keep this file private.",
        "",
        "# X / Twitter",
    ]
    for key in [
        "X_CLIENT_ID",
        "X_CLIENT_SECRET",
        "X_OAUTH2_ACCESS_TOKEN",
        "X_OAUTH2_REFRESH_TOKEN",
        "X_OAUTH2_ACCESS_TOKEN_EXPIRES_AT",
        "X_OAUTH2_SCOPE",
        "X_BEARER_TOKEN",
        "X_API_KEY",
        "X_API_SECRET",
        "X_CONSUMER_KEY",
        "X_CONSUMER_SECRET",
        "X_ACCESS_TOKEN",
        "X_ACCESS_TOKEN_SECRET",
        "X_ALLOW_OAUTH1_POSTING_FALLBACK",
        "X_MONITOR_USER_ID",
        "X_MONITOR_QUERY",
        "X_APP_PERMISSIONS",
        "X_APP_TYPE",
        "X_CALLBACK_URI",
        "X_WEBSITE_URL",
        "X_ORGANIZATION_NAME",
        "X_ORGANIZATION_URL",
        "X_TERMS_URL",
        "X_PRIVACY_URL",
        "X_REQUEST_EMAIL_FROM_USERS",
    ]:
        lines.append(f'{key}="{current.get(key, "")}"')

    lines.extend(["", "# Email"])
    for key in [
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
        "EMAIL_MAILBOX",
    ]:
        lines.append(f'{key}="{current.get(key, "")}"')

    lines.extend(["", "# AI Agent"])
    for key in [
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "PRODUCT_KNOWLEDGE_ROOTS",
        "ALLOW_OPENAI_TECHNICAL_CONTEXT",
    ]:
        lines.append(f'{key}="{current.get(key, "")}"')

    lines.extend(["", "# Feature flags"])
    for key in [
        "ENABLE_X_READ",
        "ENABLE_X_WRITE",
        "ENABLE_EMAIL_READ",
        "ENABLE_EMAIL_SEND",
        "REQUIRE_HUMAN_APPROVAL",
        "ALLOW_KEYWORD_SEARCH_AUTO_REPLY",
        "ALLOW_UNSOLICITED_DM",
        "METADATA_ONLY_LEARNING",
        "ENABLE_AUTO_TRIAGE",
        "AUTO_ARCHIVE_HIGH_CONFIDENCE_SPAM",
        "AUTO_DRAFT_RELEVANT_REPLIES",
        "AUTO_TRIAGE_CONFIDENCE_THRESHOLD",
    ]:
        lines.append(f'{key}="{current.get(key, "")}"')

    with open(path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")

    for key, value in current.items():
        if key in ENV_KEYS:
            os.environ[key] = value
    return path


def get_env(name: str, default: str | None = None) -> str | None:
    load_env_file()
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    value = get_env(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 6:
        return "***"
    return f"{value[:3]}***{value[-3:]}"
