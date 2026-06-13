from typing import Dict, List

from .claim_guard import check_claims
from .settings import feature_enabled


RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "block": 3}

EMAIL_CATEGORIES = {
    "demo request": ["demo", "walkthrough", "show me", "trial", "book a call"],
    "partnership": ["partner", "partnership", "integrate", "collaboration"],
    "support": ["support", "issue", "problem", "bug", "not working"],
    "sales lead": ["pricing", "quote", "procurement", "buy", "purchase"],
    "press/analyst": ["press", "analyst", "media", "interview"],
    "legal/compliance": ["legal", "compliance", "contract", "dpa", "terms"],
    "security": ["security", "soc 2", "iso", "pentest", "vulnerability"],
    "spam/noise": ["unsubscribe", "seo", "guest post", "crypto", "loan"],
}


def _max_risk(current: str, candidate: str) -> str:
    return candidate if RISK_ORDER[candidate] > RISK_ORDER[current] else current


def classify_email(subject: str = "", body: str = "") -> str:
    text = f"{subject}\n{body}".lower()
    for category, keywords in EMAIL_CATEGORIES.items():
        if any(keyword in text for keyword in keywords):
            return category
    return "sales lead"


def classify_action(channel: str, action_type: str, text: str, source: Dict | None = None) -> dict:
    source = source or {}
    risk_level, claim_matches = check_claims(text)
    reasons: List[str] = list(claim_matches)
    blocked = risk_level == "block"

    source_type = source.get("source_type") or source.get("type") or ""
    if action_type == "x_reply" and source_type in {"keyword_search", "x_search", "x_monitor"}:
        if not feature_enabled("ALLOW_KEYWORD_SEARCH_AUTO_REPLY"):
            risk_level = "block"
            blocked = True
            reasons.append("keyword_search_auto_reply_blocked")

    if action_type in {"x_dm", "dm"} and not feature_enabled("ALLOW_UNSOLICITED_DM"):
        risk_level = "block"
        blocked = True
        reasons.append("unsolicited_dm_blocked")

    lower_text = text.lower()
    if any(term in lower_text for term in ["confidential", "decision pack", "private customer", "signed pack"]):
        risk_level = _max_risk(risk_level, "high")
        reasons.append("possible_private_or_decision_pack_content")

    if channel == "email":
        category = classify_email(source.get("subject", ""), text)
        if category in {"legal/compliance", "security"}:
            risk_level = _max_risk(risk_level, "medium")
            reasons.append(f"escalation_category:{category}")
    else:
        category = source.get("category", "")

    return {
        "level": risk_level,
        "blocked": blocked,
        "reasons": reasons,
        "claims_checked": claim_matches,
        "category": category,
    }
