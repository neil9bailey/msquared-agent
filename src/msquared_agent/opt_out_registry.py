import json
from datetime import datetime, timezone

from .paths import writable_path


OPT_OUT_FILE = writable_path("data", "opt_out.json")


def _load_records() -> list:
    if OPT_OUT_FILE.exists():
        with open(OPT_OUT_FILE, encoding="utf-8") as file:
            return json.load(file)
    return []


def _save_records(records: list) -> None:
    with open(OPT_OUT_FILE, "w", encoding="utf-8") as file:
        json.dump(records, file, indent=2)


def add_opt_out(identifier: str, channel: str = "any", reason: str = "") -> dict:
    records = _load_records()
    normalized = identifier.strip().lower()
    for record in records:
        if record.get("identifier") == normalized and record.get("channel") in {channel, "any"}:
            return record
    record = {
        "identifier": normalized,
        "channel": channel,
        "reason": reason,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    records.append(record)
    _save_records(records)
    return record


def is_opted_out(identifier: str, channel: str | None = None) -> bool:
    if not identifier:
        return False
    normalized = identifier.strip().lower()
    for record in _load_records():
        if record.get("identifier") != normalized:
            continue
        if channel is None or record.get("channel") in {channel, "any"}:
            return True
    return False


def list_opt_outs() -> list:
    return _load_records()
