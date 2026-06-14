import json
from datetime import datetime, timezone
from typing import Dict, Any

from .audit_store import log_action
from .paths import writable_path

QUEUE_FILE = writable_path("data", "approval_queue.json")
APPROVAL_STATES = {"drafted", "needs_review", "approved", "rejected", "sent_or_posted", "archived"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def load_queue() -> list:
    if QUEUE_FILE.exists():
        with open(QUEUE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []

def save_queue(queue: list):
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2)


def _next_id(queue: list) -> str:
    numbers = []
    for item in queue:
        value = str(item.get("id", ""))
        if value.startswith("item_"):
            try:
                numbers.append(int(value.split("_", 1)[1]))
            except ValueError:
                pass
    return f"item_{max(numbers, default=0) + 1}"


def add_to_queue(item: Dict[str, Any]):
    queue = load_queue()
    item["id"] = _next_id(queue)
    _prepare_draft_versions(item)
    if item.get("status") not in APPROVAL_STATES:
        item["status"] = "needs_review" if item.get("risk_level") in {"medium", "high", "block"} else "drafted"
    item.setdefault("pipeline_state", "draft_ready")
    item["created_at"] = _now()
    queue.append(item)
    save_queue(queue)
    return item

def list_queue():
    return load_queue()


def get_approval_item(item_id: str):
    for item in load_queue():
        if item.get("id") == item_id:
            return item
    return None


def update_approval_item(item_id: str, updates: Dict[str, Any]) -> Dict[str, Any] | None:
    queue = load_queue()
    for item in queue:
        if item.get("id") == item_id:
            item.update(updates)
            item["updated_at"] = _now()
            save_queue(queue)
            return item
    return None


def _prepare_draft_versions(item: Dict[str, Any]) -> None:
    draft = item.get("draft") or item.get("final_draft") or item.get("raw_agent_draft") or ""
    source = item.get("source") or {}
    context = item.get("context") or {}
    context_source = context.get("source") or {}
    source_intake_id = (
        item.get("source_intake_id")
        or source.get("canonical_id")
        or source.get("id")
        or context_source.get("canonical_id")
        or context_source.get("id")
    )
    item.setdefault("action_type", item.get("type"))
    item.setdefault("source_intake_id", source_intake_id or "")
    item.setdefault("external_source_id", source.get("source_id") or context_source.get("source_id") or "")
    if item.get("type") == "x_reply" and not item.get("reply_to") and item.get("external_source_id"):
        item["reply_to"] = item["external_source_id"]
    item.setdefault("raw_agent_draft", draft)
    item.setdefault("final_draft", item.get("legal_revised_draft") or draft)
    item["draft"] = item.get("final_draft") or draft
    item.setdefault("draft_versions", [])
    if not item["draft_versions"]:
        item["draft_versions"].append({
            "version": "raw_agent",
            "text": item.get("raw_agent_draft", ""),
            "created_at": _now(),
            "source": "MSquared Agent",
        })
    item.setdefault("selected_version", "final")


def approve_item(item_id: str, approver: str = "human"):
    queue = load_queue()
    for item in queue:
        if item.get("id") == item_id:
            if item.get("status") not in {"drafted", "needs_review"}:
                raise ValueError(f"Only drafted or needs_review items can be approved. Current status: {item.get('status')}")
            if item.get("risk_level") == "block":
                raise ValueError("Blocked items cannot be approved without changing the draft.")
            item["status"] = "approved"
            item["approved_by"] = approver
            item["approved_at"] = _now()
            item["pipeline_state"] = "approved"
            item["final_draft"] = item.get("final_draft") or item.get("draft", "")
            item["draft"] = item["final_draft"]
            save_queue(queue)
            try:
                from .feedback_store import record_feedback_for_item

                record_feedback_for_item(item, "approved")
            except Exception:
                pass
            log_action({
                "action": "approval_granted",
                "approval_item_id": item_id,
                "channel": item.get("channel"),
                "approver": approver,
                "final_action_status": "approved",
            })
            return item
    return None

def reject_item(item_id: str, reason: str = "", rejected_by: str = "human"):
    queue = load_queue()
    for item in queue:
        if item.get("id") == item_id:
            if item.get("status") not in {"drafted", "needs_review"}:
                raise ValueError(f"Only drafted or needs_review items can be rejected. Current status: {item.get('status')}")
            item["status"] = "rejected"
            item["pipeline_state"] = "rejected"
            item["rejected_by"] = rejected_by
            item["rejection_reason"] = reason
            item["rejected_at"] = _now()
            save_queue(queue)
            try:
                from .feedback_store import record_feedback_for_item

                record_feedback_for_item(item, "rejected", reason_tags=[reason] if reason else item.get("risks", []))
            except Exception:
                pass
            log_action({
                "action": "approval_rejected",
                "approval_item_id": item_id,
                "channel": item.get("channel"),
                "rejected_by": rejected_by,
                "reason": reason,
                "final_action_status": "rejected",
            })
            return item
    return None


def mark_sent_or_posted(item_id: str, final_status: str = "sent_or_posted"):
    if final_status != "sent_or_posted":
        raise ValueError("mark_sent_or_posted only accepts final_status='sent_or_posted'.")
    queue = load_queue()
    for item in queue:
        if item.get("id") == item_id:
            if item.get("status") != "approved":
                raise ValueError(f"Only approved items can be finalized. Current status: {item.get('status')}")
            item["status"] = final_status
            item["pipeline_state"] = final_status
            item["finalized_at"] = _now()
            save_queue(queue)
            return item
    return None
