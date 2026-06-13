import hashlib
import json
import os
import re
from typing import Any


SECRET_KEY_MARKERS = (
    "PASSWORD",
    "SECRET",
    "TOKEN",
    "BEARER",
    "API_KEY",
    "API_SECRET",
    "CONSUMER_KEY",
    "CONSUMER_SECRET",
    "CLIENT_SECRET",
    "ACCESS_TOKEN",
)

CONTENT_KEYS = {
    "body",
    "content",
    "draft",
    "draft_preview",
    "draft_text",
    "payload",
    "prompt",
    "system_prompt",
    "text",
}

REDACTED = "[REDACTED]"
CONTENT_OMITTED = "[CONTENT_OMITTED]"


def _is_secret_key(key: str) -> bool:
    normalized = key.upper().replace("-", "_")
    return any(marker in normalized for marker in SECRET_KEY_MARKERS)


def _is_content_key(key: str) -> bool:
    return key.lower() in CONTENT_KEYS


def _known_secret_values() -> list[str]:
    values = []
    for key, value in os.environ.items():
        if _is_secret_key(key) and value and len(value) >= 6:
            values.append(value)
    values.sort(key=len, reverse=True)
    return values


def redact_text(value: str) -> str:
    redacted = value
    for secret in _known_secret_values():
        redacted = redacted.replace(secret, REDACTED)

    redacted = re.sub(
        r"(?i)(bearer\s+)[A-Za-z0-9%._~+\-/=]+",
        rf"\1{REDACTED}",
        redacted,
    )
    redacted = re.sub(
        r"(?i)((?:password|secret|token|api[_-]?key|api[_-]?secret|access[_-]?token|client[_-]?secret|consumer[_-]?secret)=)[^&\s]+",
        rf"\1{REDACTED}",
        redacted,
    )
    redacted = re.sub(
        r"([A-Z0-9._%+-]{2})[A-Z0-9._%+-]*(@[A-Z0-9.-]+\.[A-Z]{2,})",
        r"\1***\2",
        redacted,
        flags=re.IGNORECASE,
    )
    return redacted


def content_digest(value: Any) -> dict:
    if isinstance(value, str):
        normalized = value
    else:
        normalized = json.dumps(value, sort_keys=True, default=str)
    return {
        "omitted": CONTENT_OMITTED,
        "sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        "length": len(normalized),
    }


def sanitize_for_log(value: Any) -> Any:
    return _sanitize(value, omit_content=True)


def sanitize_for_audit(value: Any) -> Any:
    return _sanitize(value, omit_content=True)


def _sanitize(value: Any, omit_content: bool) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, nested_value in value.items():
            key_text = str(key)
            if _is_secret_key(key_text):
                sanitized[key] = REDACTED
            elif omit_content and _is_content_key(key_text):
                sanitized[key] = content_digest(nested_value)
            else:
                sanitized[key] = _sanitize(nested_value, omit_content)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item, omit_content) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize(item, omit_content) for item in value)
    if isinstance(value, str):
        return redact_text(value)
    return value
