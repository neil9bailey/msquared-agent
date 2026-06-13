import json
from datetime import datetime, timezone
from uuid import uuid4

from .paths import writable_path
from .redaction import sanitize_for_log


APP_LOG_FILE = writable_path("data", "app.log.jsonl")


def log_event(event: str, level: str = "info", message: str = "", details: dict | None = None) -> dict:
    entry = {
        "event_id": f"log_{uuid4().hex}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level.lower(),
        "event": event,
        "message": message,
        "details": details or {},
    }
    sanitized = sanitize_for_log(entry)
    with open(APP_LOG_FILE, "a", encoding="utf-8") as file:
        file.write(json.dumps(sanitized, default=str) + "\n")
    return sanitized


def read_log_events(limit: int = 200) -> list:
    if not APP_LOG_FILE.exists():
        return []
    events = []
    with open(APP_LOG_FILE, encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            try:
                events.append(sanitize_for_log(json.loads(line)))
            except json.JSONDecodeError:
                events.append({
                    "event_id": f"log_{uuid4().hex}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": "warning",
                    "event": "app_log_parse_failed",
                    "message": "A log row could not be parsed.",
                    "details": {},
                })
    if limit and len(events) > limit:
        return events[-limit:]
    return events


def latest_event(prefix: str, limit: int = 50) -> dict | None:
    for event in reversed(read_log_events(limit)):
        if str(event.get("event", "")).startswith(prefix):
            return event
    return None
