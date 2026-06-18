import re
from datetime import datetime, timezone
from typing import Any

from .app_log import log_event
from .env_loader import get_env
from .intake_store import list_intake, update_intake_item
from .settings import load_feature_flags
from .text_hygiene import contains_non_latin_text, display_excerpt, normalize_text, product_excerpt


MUTABLE_TRIAGE_STATUSES = {
    "new",
    "needs_reply",
    "no_reply_needed",
    "needs_review",
    "spam",
    "unrelated",
    "low_quality",
}

DIRECT_X_SOURCES = {"x_mention", "x_reply", "x_dm"}
SEARCH_X_SOURCES = {"keyword_search", "x_search", "x_monitor"}
EMAIL_SOURCES = {"website_contact", "email", "contact_form"}

PRODUCT_PATTERNS = {
    "diiac": (
        (r"\bdiiac\b", 0.55, "diiac_named"),
        (r"\bdecision intelligence\b", 0.24, "decision_intelligence"),
        (r"\bdecision assurance\b", 0.22, "decision_assurance"),
        (r"\bgoverned decision", 0.20, "governed_decisions"),
        (r"\bai governance\b", 0.20, "ai_governance"),
        (r"\bevidence[- ]bound\b", 0.18, "evidence_bound"),
        (r"\baudit(?:able)?\b", 0.12, "auditability"),
        (r"\bcompliance\b", 0.12, "compliance"),
        (r"\bassurance\b", 0.12, "assurance"),
        (r"\benterprise ai\b", 0.12, "enterprise_ai"),
    ),
    "m_squared": (
        (r"\bmsquared\b", 0.55, "msquared_named"),
        (r"\bm[- ]?squared\b", 0.55, "m_squared_named"),
        (r"(?<![a-z0-9])m2(?![a-z0-9])", 0.48, "m2_named"),
        (r"\bmodel evaluation\b", 0.22, "model_evaluation"),
        (r"\binterpretability\b", 0.22, "interpretability"),
        (r"\breasoning signals?\b", 0.18, "reasoning_signals"),
        (r"\bagent architecture\b", 0.18, "agent_architecture"),
        (r"\bai assurance\b", 0.18, "ai_assurance"),
    ),
}

SPAM_PATTERNS = (
    (r"\bairdrop\b", 0.36, "airdrop"),
    (r"\bgiveaway\b", 0.30, "giveaway"),
    (r"\bfree followers?\b", 0.42, "free_followers"),
    (r"\bonlyfans\b", 0.55, "adult_spam"),
    (r"\badult\b", 0.32, "adult"),
    (r"\bcasino\b", 0.34, "casino"),
    (r"\bbet(?:ting)?\b", 0.26, "betting"),
    (r"\bcrypto\b", 0.18, "crypto"),
    (r"\bforex\b", 0.30, "forex"),
    (r"\bloan\b", 0.24, "loan"),
    (r"\binvest(?:ment|ing)\b", 0.20, "investment_pitch"),
    (r"\bseo\b", 0.28, "seo_pitch"),
    (r"\bpromot(?:e|ion)\b", 0.22, "promotion_pitch"),
    (r"\bdm us\b", 0.18, "generic_dm_pitch"),
    (r"\bclick here\b", 0.22, "clickbait"),
    (r"\bwhatsapp\b", 0.24, "whatsapp_pitch"),
    (r"\btelegram\b", 0.22, "telegram_pitch"),
)

ESCALATION_PATTERNS = (
    (r"\blegal\b", 0.35, "legal"),
    (r"\blawsuit\b", 0.50, "lawsuit"),
    (r"\bregulator(?:y)?\b", 0.35, "regulatory"),
    (r"\bpress\b", 0.28, "press"),
    (r"\bjournalist\b", 0.28, "press"),
    (r"\banalyst\b", 0.22, "analyst"),
    (r"\bsecurity\b", 0.25, "security"),
    (r"\bbreach\b", 0.45, "breach"),
    (r"\bvulnerab(?:ility|le)\b", 0.42, "vulnerability"),
    (r"\bcontract\b", 0.25, "contract"),
    (r"\bcomplaint\b", 0.30, "complaint"),
    (r"\bprivate\b", 0.22, "private_material"),
)

QUESTION_PATTERNS = (
    r"\?",
    r"\bhow\b",
    r"\bwhat\b",
    r"\bcan you\b",
    r"\bcould you\b",
    r"\bplease\b",
    r"\binterested\b",
    r"\bmore information\b",
    r"\bbook\b.*\bcall\b",
    r"\bdemo\b",
)


def triage_intake_item(item: dict[str, Any]) -> dict[str, Any]:
    text = _item_text(item)
    lowered = text.lower()
    channel = (item.get("channel") or "").lower()
    source_type = (item.get("source_type") or item.get("type") or "").lower()
    direct_source = channel == "email" or source_type in DIRECT_X_SOURCES
    search_source = channel == "x" and source_type in SEARCH_X_SOURCES

    product_score, product_tags, product_match = _product_signal(lowered)
    spam_score, spam_tags = _pattern_score(lowered, SPAM_PATTERNS)
    escalation_score, escalation_tags = _pattern_score(lowered, ESCALATION_PATTERNS)
    question_score = _question_score(lowered)
    link_count = len(re.findall(r"https?://|t\.co/", lowered))
    hashtag_count = len(re.findall(r"#\w+", lowered))
    mention_count = len(re.findall(r"@\w+", lowered))
    text_length = len(normalize_text(text))
    non_latin = contains_non_latin_text(text)

    reason_tags = list(dict.fromkeys(product_tags + spam_tags + escalation_tags))
    if link_count >= 3:
        spam_score += 0.18
        reason_tags.append("many_links")
    if hashtag_count >= 6:
        spam_score += 0.16
        reason_tags.append("hashtag_heavy")
    if mention_count >= 5:
        spam_score += 0.15
        reason_tags.append("mention_heavy")
    if non_latin and product_score < 0.15:
        spam_score += 0.10
        reason_tags.append("mixed_or_non_latin_without_product_signal")
    if text_length < 12:
        reason_tags.append("too_little_context")

    relevance_score = min(product_score + (0.12 if channel == "email" else 0.0), 1.0)
    spam_score = min(spam_score, 1.0)
    escalation_score = min(escalation_score, 1.0)
    question_score = min(question_score, 1.0)

    label = "unknown_review"
    recommended_action = "review"
    waiting_reply = False

    if escalation_score >= 0.35 and (direct_source or relevance_score >= 0.25):
        label = "escalate"
        recommended_action = "escalate"
        reason_tags.append("human_escalation_required")
    elif spam_score >= 0.62 and relevance_score < 0.28:
        label = "spam"
        recommended_action = "archive"
    elif text_length < 12 and not product_score:
        label = "low_quality"
        recommended_action = "archive"
    elif relevance_score < 0.18 and search_source:
        label = "unrelated"
        recommended_action = "archive"
    elif relevance_score < 0.18 and not direct_source:
        label = "unrelated"
        recommended_action = "archive"
    elif direct_source and spam_score < 0.62 and (
        channel == "email" or relevance_score >= 0.25 or (channel == "x" and product_score >= 0.15 and question_score >= 0.18)
    ):
        label = "needs_reply"
        recommended_action = "generate_reply"
        waiting_reply = True
    elif search_source and relevance_score >= 0.25:
        label = "relevant_no_reply_needed"
        recommended_action = "consider_original_post"
    elif relevance_score >= 0.25:
        label = "needs_reply" if direct_source else "relevant_no_reply_needed"
        recommended_action = "generate_reply" if direct_source else "consider_original_post"
        waiting_reply = direct_source

    confidence = _confidence(label, relevance_score, spam_score, escalation_score, question_score, direct_source)
    if label == "needs_reply" and search_source and not _keyword_search_auto_reply_allowed():
        label = "relevant_no_reply_needed"
        recommended_action = "consider_original_post"
        waiting_reply = False
        reason_tags.append("keyword_search_reply_blocked")

    return {
        "label": label,
        "recommended_action": recommended_action,
        "waiting_reply": waiting_reply,
        "confidence": round(confidence, 2),
        "relevance_score": round(relevance_score, 2),
        "spam_score": round(spam_score, 2),
        "escalation_score": round(escalation_score, 2),
        "product_match": product_match,
        "reason_tags": sorted(set(reason_tags)),
        "summary": product_excerpt(text, 220) if product_score else display_excerpt(text, 220),
        "source_type": source_type,
        "triaged_at": datetime.now(timezone.utc).isoformat(),
    }


def triage_all_intake(auto_archive: bool = False, confidence_threshold: float | None = None) -> dict[str, Any]:
    threshold = _confidence_threshold(confidence_threshold)
    items = list_intake("all")
    result = {
        "total_count": len(items),
        "triaged_count": 0,
        "updated_count": 0,
        "waiting_reply_count": 0,
        "auto_archived_count": 0,
        "label_counts": {},
        "recommended_action_counts": {},
        "confidence_threshold": threshold,
    }
    log_event(
        "intake_triage_started",
        "info",
        "Intake triage started.",
        {"item_count": len(items), "auto_archive": auto_archive, "confidence_threshold": threshold},
    )
    for item in items:
        if item.get("status") == "archived":
            continue
        triage = triage_intake_item(item)
        result["triaged_count"] += 1
        result["label_counts"][triage["label"]] = result["label_counts"].get(triage["label"], 0) + 1
        action = triage["recommended_action"]
        result["recommended_action_counts"][action] = result["recommended_action_counts"].get(action, 0) + 1
        if triage["waiting_reply"]:
            result["waiting_reply_count"] += 1

        new_status = _status_for_triage(item, triage)
        status_is_mutable = item.get("status", "new") in MUTABLE_TRIAGE_STATUSES
        if auto_archive and status_is_mutable and action == "archive" and triage["confidence"] >= threshold:
            new_status = "archived"
            triage["archived_by_agent"] = True
            result["auto_archived_count"] += 1

        updates = {"triage": triage}
        if status_is_mutable or new_status == "archived":
            updates["status"] = new_status
        existing = item.get("triage") or {}
        if existing.get("label") != triage["label"] or item.get("status") != updates.get("status", item.get("status")):
            result["updated_count"] += 1
        updated = update_intake_item(item["id"], updates)
        log_event(
            "intake_triaged",
            "info",
            "Intake item triaged.",
            {
                "intake_id": item.get("id"),
                "canonical_id": item.get("canonical_id"),
                "channel": item.get("channel"),
                "label": triage["label"],
                "recommended_action": action,
                "waiting_reply": triage["waiting_reply"],
                "confidence": triage["confidence"],
                "status": (updated or item).get("status"),
            },
        )
        if triage.get("archived_by_agent"):
            log_event(
                "intake_auto_archived",
                "info",
                "High-confidence spam or unrelated intake was archived locally.",
                {
                    "intake_id": item.get("id"),
                    "canonical_id": item.get("canonical_id"),
                    "label": triage["label"],
                    "confidence": triage["confidence"],
                },
            )
    log_event("intake_triage_completed", "info", "Intake triage completed.", result)
    return result


def waiting_reply_items() -> list[dict[str, Any]]:
    return [
        item for item in list_intake("all")
        if item.get("status") != "archived" and (item.get("triage") or {}).get("waiting_reply")
    ]


def intake_triage_status() -> dict[str, Any]:
    items = list_intake("all")
    labels: dict[str, int] = {}
    actions: dict[str, int] = {}
    waiting = 0
    untriaged = 0
    archive_candidates = 0
    for item in items:
        triage = item.get("triage") or {}
        label = triage.get("label")
        action = triage.get("recommended_action")
        if not label:
            untriaged += 1
            continue
        labels[label] = labels.get(label, 0) + 1
        if action:
            actions[action] = actions.get(action, 0) + 1
        if triage.get("waiting_reply") and item.get("status") != "archived":
            waiting += 1
        if action == "archive" and item.get("status") != "archived":
            archive_candidates += 1
    return {
        "triaged_count": len(items) - untriaged,
        "untriaged_count": untriaged,
        "label_counts": labels,
        "recommended_action_counts": actions,
        "waiting_reply_count": waiting,
        "local_archive_candidate_count": archive_candidates,
    }


def _item_text(item: dict[str, Any]) -> str:
    parts = [
        item.get("subject", ""),
        item.get("text", "") or item.get("body", ""),
        item.get("from", ""),
        item.get("author", ""),
    ]
    return normalize_text("\n".join(str(part) for part in parts if part))


def _product_signal(lowered: str) -> tuple[float, list[str], str]:
    scores: dict[str, float] = {"diiac": 0.0, "m_squared": 0.0}
    tags: list[str] = []
    for product, patterns in PRODUCT_PATTERNS.items():
        for pattern, weight, tag in patterns:
            if re.search(pattern, lowered):
                scores[product] = min(scores[product] + weight, 1.0)
                tags.append(tag)
    total = min(sum(scores.values()), 1.0)
    if scores["diiac"] and scores["m_squared"]:
        product_match = "both"
    elif scores["diiac"]:
        product_match = "DIIaC"
    elif scores["m_squared"]:
        product_match = "M Squared"
    else:
        product_match = "none"
    return total, tags, product_match


def _pattern_score(lowered: str, patterns: tuple[tuple[str, float, str], ...]) -> tuple[float, list[str]]:
    score = 0.0
    tags: list[str] = []
    for pattern, weight, tag in patterns:
        if re.search(pattern, lowered):
            score += weight
            tags.append(tag)
    return min(score, 1.0), tags


def _question_score(lowered: str) -> float:
    score = 0.0
    for pattern in QUESTION_PATTERNS:
        if re.search(pattern, lowered):
            score += 0.18
    return min(score, 1.0)


def _confidence(
    label: str,
    relevance_score: float,
    spam_score: float,
    escalation_score: float,
    question_score: float,
    direct_source: bool,
) -> float:
    if label == "spam":
        return min(0.55 + spam_score, 0.98)
    if label == "unrelated":
        return 0.88 if relevance_score < 0.08 else 0.74
    if label == "low_quality":
        return 0.80
    if label == "escalate":
        return min(0.58 + escalation_score, 0.96)
    if label == "needs_reply":
        return min(0.48 + relevance_score + question_score + (0.12 if direct_source else 0.0), 0.97)
    if label == "relevant_no_reply_needed":
        return min(0.52 + relevance_score, 0.92)
    return 0.55


def _status_for_triage(item: dict[str, Any], triage: dict[str, Any]) -> str:
    current = item.get("status") or "new"
    if current not in MUTABLE_TRIAGE_STATUSES:
        return current
    return {
        "needs_reply": "needs_reply",
        "relevant_no_reply_needed": "no_reply_needed",
        "spam": "spam",
        "unrelated": "unrelated",
        "low_quality": "low_quality",
        "escalate": "needs_review",
        "unknown_review": "needs_review",
    }.get(triage["label"], current)


def _keyword_search_auto_reply_allowed() -> bool:
    return bool(load_feature_flags().get("ALLOW_KEYWORD_SEARCH_AUTO_REPLY"))


def _confidence_threshold(value: float | None = None) -> float:
    if value is None:
        raw = get_env("AUTO_TRIAGE_CONFIDENCE_THRESHOLD", "0.90") or "0.90"
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = 0.90
    if value != value:
        return 0.90
    return min(max(value, 0.50), 0.99)
