import difflib
import json
from datetime import datetime, timezone
from pathlib import Path

from .paths import writable_path


FEEDBACK_FILE = writable_path("data", "agent_feedback.jsonl")


def record_feedback(
    intake_id: str = "",
    draft_id: str = "",
    outcome: str = "",
    reason_tags: list[str] | None = None,
    human_edits_delta: str = "",
    action_type: str = "",
    final_text: str = "",
    knowledge_sources_used: list[dict] | None = None,
    legal_review_result: dict | None = None,
) -> dict:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "intake_id": intake_id or "",
        "draft_id": draft_id or "",
        "outcome": outcome or "",
        "reason_tags": reason_tags or [],
        "human_edits_delta": human_edits_delta or "",
        "action_type": action_type or "",
        "final_text": final_text or "",
        "knowledge_sources_used": knowledge_sources_used or [],
        "legal_review_result": legal_review_result or {},
    }
    FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(FEEDBACK_FILE, "a", encoding="utf-8") as file:
        file.write(json.dumps(entry, default=str) + "\n")
    return entry


def record_feedback_for_item(item: dict, outcome: str, reason_tags: list[str] | None = None, human_edits_delta: str = "") -> dict:
    return record_feedback(
        intake_id=item.get("source_intake_id", ""),
        draft_id=item.get("id", ""),
        outcome=outcome,
        reason_tags=reason_tags or item.get("risks", []),
        human_edits_delta=human_edits_delta or item.get("human_edits_delta", ""),
        action_type=item.get("action_type") or item.get("type", ""),
        final_text=item.get("final_draft") or item.get("draft", ""),
        knowledge_sources_used=item.get("knowledge_used", []),
        legal_review_result=item.get("legal_review", {}),
    )


def read_feedback(limit: int | None = None) -> list[dict]:
    if not FEEDBACK_FILE.exists():
        return []
    rows = []
    with open(FEEDBACK_FILE, encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if limit and len(rows) > limit:
        return rows[-limit:]
    return rows


def similar_approved_examples(query: str, action_type: str = "", limit: int = 3) -> list[dict]:
    query = query or ""
    candidates = []
    for row in read_feedback():
        if row.get("outcome") not in {"approved", "edited"}:
            continue
        if action_type and row.get("action_type") and row.get("action_type") != action_type:
            continue
        text = row.get("final_text") or ""
        score = _similarity(query, text)
        if score > 0:
            candidates.append((score, row))
    candidates.sort(key=lambda item: item[0], reverse=True)
    examples = []
    for score, row in candidates[:limit]:
        examples.append({
            "draft_id": row.get("draft_id"),
            "intake_id": row.get("intake_id"),
            "action_type": row.get("action_type"),
            "score": round(score, 4),
            "final_text": row.get("final_text", ""),
            "reason_tags": row.get("reason_tags", []),
        })
    return examples


def feedback_summary() -> dict:
    rows = read_feedback()
    outcomes: dict[str, int] = {}
    reason_tags: dict[str, int] = {}
    for row in rows:
        outcome = row.get("outcome", "unknown")
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        for tag in row.get("reason_tags", []):
            reason_tags[tag] = reason_tags.get(tag, 0) + 1
    return {
        "feedback_path": str(FEEDBACK_FILE),
        "record_count": len(rows),
        "outcomes": outcomes,
        "top_reason_tags": sorted(reason_tags.items(), key=lambda item: item[1], reverse=True)[:8],
    }


def clear_feedback(path: Path | None = None) -> None:
    target = path or FEEDBACK_FILE
    if target.exists():
        target.unlink()


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    left_words = set(left.lower().split())
    right_words = set(right.lower().split())
    overlap = len(left_words & right_words) / max(len(left_words | right_words), 1)
    sequence = difflib.SequenceMatcher(None, left.lower(), right.lower()).ratio()
    return max(overlap, sequence * 0.5)
