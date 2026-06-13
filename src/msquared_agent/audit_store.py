import json
from uuid import uuid4
from datetime import datetime, timezone

from .paths import writable_path
from .redaction import sanitize_for_audit

AUDIT_FILE = writable_path("data", "audit.log.jsonl")

def log_action(action: dict):
    entry = {
        "action_id": action.get("action_id") or f"audit_{uuid4().hex}",
        **action,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    entry = sanitize_for_audit(entry)
    with open(AUDIT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def read_audit_records() -> list:
    if not AUDIT_FILE.exists():
        return []
    with open(AUDIT_FILE, encoding="utf-8") as file:
        return [sanitize_for_audit(json.loads(line)) for line in file if line.strip()]
