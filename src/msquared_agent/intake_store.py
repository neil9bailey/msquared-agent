import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from .paths import writable_path


INTAKE_FILE = writable_path("data", "inbound_items.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_intake() -> List[Dict[str, Any]]:
    if INTAKE_FILE.exists():
        with open(INTAKE_FILE, encoding="utf-8") as file:
            return json.load(file)
    return []


def save_intake(items: List[Dict[str, Any]]) -> None:
    with open(INTAKE_FILE, "w", encoding="utf-8") as file:
        json.dump(items, file, indent=2)


def _next_id(items: List[Dict[str, Any]]) -> str:
    numbers = []
    for item in items:
        value = str(item.get("id", ""))
        if value.startswith("in_"):
            try:
                numbers.append(int(value.split("_", 1)[1]))
            except ValueError:
                pass
    return f"in_{max(numbers, default=0) + 1}"


def add_intake_item(item: Dict[str, Any]) -> Dict[str, Any]:
    items = load_intake()
    source_id = item.get("source_id")
    channel = item.get("channel")
    if source_id:
        for existing in items:
            if existing.get("source_id") == source_id and existing.get("channel") == channel:
                return existing

    item = dict(item)
    item.setdefault("id", _next_id(items))
    item.setdefault("status", "new")
    item.setdefault("received_at", _now())
    item.setdefault("source_type", item.get("type", "manual"))
    items.append(item)
    save_intake(items)
    return item


def list_intake(status: str | None = None) -> List[Dict[str, Any]]:
    items = load_intake()
    if status and status != "all":
        return [item for item in items if item.get("status") == status]
    return items


def get_intake_item(item_id: str) -> Dict[str, Any] | None:
    for item in load_intake():
        if item.get("id") == item_id:
            return item
    return None


def update_intake_status(item_id: str, status: str) -> Dict[str, Any] | None:
    items = load_intake()
    for item in items:
        if item.get("id") == item_id:
            item["status"] = status
            item["updated_at"] = _now()
            save_intake(items)
            return item
    return None
