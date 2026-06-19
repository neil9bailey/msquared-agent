from datetime import datetime, timezone
from typing import Any

from .approval_queue import list_queue
from .intake_store import list_intake
from .intake_triage import intake_triage_status
from .text_hygiene import display_excerpt, product_excerpt


def build_monitor_intelligence_snapshot(intake_limit: int = 40, draft_limit: int = 20) -> dict[str, Any]:
    intake_items = list_intake("all")
    queue_items = list_queue()
    active_intake = [item for item in intake_items if item.get("status") != "archived"]
    waiting = [
        item for item in active_intake
        if item.get("status") == "needs_reply" or (item.get("triage") or {}).get("waiting_reply")
    ]
    archive_candidates = [
        item for item in active_intake
        if (item.get("triage") or {}).get("recommended_action") == "archive"
    ]
    escalation = [
        item for item in active_intake
        if (item.get("triage") or {}).get("recommended_action") == "escalate"
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "intake_total": len(intake_items),
            "intake_active": len(active_intake),
            "waiting_reply": len(waiting),
            "archive_candidates": len(archive_candidates),
            "escalation": len(escalation),
            "approval_queue": len(queue_items),
        },
        "triage_status": intake_triage_status(),
        "waiting_replies": [_intake_digest(item) for item in _recent(waiting, intake_limit)],
        "archive_candidates": [_intake_digest(item) for item in _recent(archive_candidates, min(12, intake_limit))],
        "escalations": [_intake_digest(item) for item in _recent(escalation, min(12, intake_limit))],
        "recent_intake": [_intake_digest(item) for item in _recent(active_intake, intake_limit)],
        "recent_drafts": [_draft_digest(item) for item in _recent(queue_items, draft_limit)],
        "operator_guidance": [
            "Use waiting_replies to decide what needs MSquared response drafts.",
            "Use archive_candidates as local noise/spam candidates only; do not delete external posts or emails.",
            "Use escalations for legal, security, press, contract, complaint, or sensitive-material handoff.",
            "Public X/email actions still require approval, preflight, and operator confirmation.",
        ],
    }


def format_monitor_intelligence(snapshot: dict[str, Any] | None, max_items: int = 12) -> str:
    if not snapshot:
        return "Monitor intelligence: not included."
    counts = snapshot.get("counts") or {}
    triage = snapshot.get("triage_status") or {}
    lines = [
        "Monitor intelligence:",
        (
            f"active intake={counts.get('intake_active', 0)} | "
            f"waiting replies={counts.get('waiting_reply', 0)} | "
            f"archive candidates={counts.get('archive_candidates', 0)} | "
            f"escalations={counts.get('escalation', 0)} | "
            f"approval queue={counts.get('approval_queue', 0)}"
        ),
        f"triage labels={triage.get('label_counts', {})}",
    ]
    waiting = snapshot.get("waiting_replies") or []
    if waiting:
        lines.append("")
        lines.append("Waiting replies:")
        for item in waiting[:max_items]:
            lines.append(_format_intake_line(item))
    escalations = snapshot.get("escalations") or []
    if escalations:
        lines.append("")
        lines.append("Escalations:")
        for item in escalations[:max_items]:
            lines.append(_format_intake_line(item))
    archive_candidates = snapshot.get("archive_candidates") or []
    if archive_candidates:
        lines.append("")
        lines.append("Archive candidates:")
        for item in archive_candidates[:max_items]:
            lines.append(_format_intake_line(item))
    recent = snapshot.get("recent_intake") or []
    if recent:
        lines.append("")
        lines.append("Recent active intake:")
        for item in recent[:max_items]:
            lines.append(_format_intake_line(item))
    return "\n".join(lines)


def _recent(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: item.get("updated_at") or item.get("received_at") or "", reverse=True)[:limit]


def _intake_digest(item: dict[str, Any]) -> dict[str, Any]:
    triage = item.get("triage") or {}
    channel = item.get("channel") or ""
    text = item.get("text") or item.get("body") or ""
    excerpt = product_excerpt(text, 900) if channel == "x" else display_excerpt(text, 900)
    return {
        "id": item.get("id"),
        "canonical_id": item.get("canonical_id"),
        "channel": channel,
        "source_type": item.get("source_type") or item.get("type"),
        "source_id": item.get("source_id"),
        "status": item.get("status"),
        "from": item.get("from") or item.get("author"),
        "subject": display_excerpt(item.get("subject"), 180),
        "text_excerpt": excerpt,
        "received_at": item.get("received_at"),
        "conversation_id": item.get("conversation_id"),
        "triage": {
            "label": triage.get("label"),
            "recommended_action": triage.get("recommended_action"),
            "waiting_reply": triage.get("waiting_reply"),
            "confidence": triage.get("confidence"),
            "product_match": triage.get("product_match"),
            "reason_tags": triage.get("reason_tags", []),
        },
    }


def _draft_digest(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "channel": item.get("channel"),
        "type": item.get("type"),
        "status": item.get("status"),
        "pipeline_state": item.get("pipeline_state"),
        "risk_level": item.get("risk_level"),
        "source_intake_id": item.get("source_intake_id"),
        "created_at": item.get("created_at"),
        "draft_excerpt": display_excerpt(item.get("final_draft") or item.get("draft"), 700),
    }


def _format_intake_line(item: dict[str, Any]) -> str:
    triage = item.get("triage") or {}
    subject = f" | subject={item.get('subject')}" if item.get("subject") else ""
    return (
        f"- {item.get('canonical_id') or item.get('id')} | {item.get('channel')}/{item.get('source_type')} | "
        f"status={item.get('status')} | triage={triage.get('label')}({triage.get('confidence')}) | "
        f"action={triage.get('recommended_action')} | from={item.get('from') or 'unknown'}{subject} | "
        f"text={item.get('text_excerpt') or ''}"
    )
