def detect_action_for_intake(item: dict | None) -> dict:
    item = item or {}
    channel = item.get("channel") or ""
    source_type = item.get("source_type") or item.get("type") or ""
    canonical_id = item.get("canonical_id") or item.get("id") or ""

    if not item:
        return {
            "action_type": "",
            "label": "No intake selected",
            "recommended_next_step": "Select an intake item to start the governed pipeline.",
            "confidence": "none",
            "requires_source_id": False,
            "source_intake_id": "",
        }

    if channel == "email":
        return {
            "action_type": "email_response",
            "label": "Email Response",
            "recommended_next_step": "Generate an MSquared email response draft for legal review.",
            "confidence": "high",
            "requires_source_id": False,
            "source_intake_id": canonical_id,
        }

    if channel == "x" and source_type in {"x_mention", "x_reply"}:
        return {
            "action_type": "x_reply",
            "label": "X Reply",
            "recommended_next_step": "Generate an MSquared reply tied to the source X post id.",
            "confidence": "high" if item.get("source_id") else "medium",
            "requires_source_id": True,
            "source_intake_id": canonical_id,
        }

    if channel == "x" and source_type in {"keyword_search", "x_search", "x_monitor"}:
        return {
            "action_type": "x_post",
            "label": "X Post",
            "recommended_next_step": "Generate an original X post. Do not auto-reply to keyword/search intake.",
            "confidence": "medium",
            "requires_source_id": False,
            "source_intake_id": canonical_id,
        }

    if channel == "x":
        return {
            "action_type": "x_post",
            "label": "X Post",
            "recommended_next_step": "Generate an original X post from this intake context.",
            "confidence": "medium",
            "requires_source_id": False,
            "source_intake_id": canonical_id,
        }

    return {
        "action_type": "manual",
        "label": "Manual Review",
        "recommended_next_step": "Review this item manually before drafting.",
        "confidence": "low",
        "requires_source_id": False,
        "source_intake_id": canonical_id,
    }


def action_summary(item: dict | None, draft: dict | None = None) -> str:
    action = detect_action_for_intake(item)
    parts = [
        f"Intake: {action.get('source_intake_id') or 'none'}",
        f"Detected action: {action.get('label')}",
        f"Confidence: {action.get('confidence')}",
        f"Next: {action.get('recommended_next_step')}",
    ]
    if item:
        subject = item.get("subject") or item.get("text") or ""
        if subject:
            parts.append(f"Summary: {_truncate(subject.replace(chr(10), ' '), 180)}")
    if draft:
        parts.extend([
            f"Draft: {draft.get('id')}",
            f"Draft status: {draft.get('status')}",
            f"Pipeline: {draft.get('pipeline_state', 'draft_ready')}",
        ])
    return "\n".join(parts)


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 3].rstrip() + "..."
