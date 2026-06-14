import re

from .app_log import log_event
from .approval_queue import get_approval_item, update_approval_item
from .claim_guard import check_claims
from .risk_classifier import classify_action


def review_approval_item(item_id: str) -> dict:
    item = get_approval_item(item_id)
    if not item:
        raise ValueError(f"Approval item not found: {item_id}")
    review = review_draft(item)
    updates = {"legal_review": review}
    if review["decision"] in {"recommend_changes", "require_changes"} and review.get("revised_draft"):
        revised = review["revised_draft"]
        versions = list(item.get("draft_versions", []))
        versions.append({
            "version": "legal_revised",
            "text": revised,
            "source": "Legal Agent",
            "rationale": review.get("rationale", ""),
        })
        updates.update({
            "legal_revised_draft": revised,
            "final_draft": revised,
            "draft": revised,
            "draft_versions": versions,
            "selected_version": "legal_revised",
            "pipeline_state": "legal_recommended_changes",
        })
    elif review["decision"] == "block":
        updates["pipeline_state"] = "legal_blocked"
        updates["status"] = "needs_review"
    else:
        updates["pipeline_state"] = "legal_passed"

    updated = update_approval_item(item_id, updates)
    event = {
        "pass": "legal_review_passed",
        "recommend_changes": "legal_review_recommended_changes",
        "require_changes": "legal_review_recommended_changes",
        "block": "legal_review_blocked",
    }[review["decision"]]
    log_event(
        event,
        "warning" if review["decision"] != "pass" else "info",
        "Legal Agent review completed.",
        {
            "approval_item_id": item_id,
            "decision": review["decision"],
            "changed": review.get("changed", False),
            "risk_tags": review.get("risk_tags", []),
        },
    )
    return updated or item


def review_draft(item: dict) -> dict:
    draft = item.get("final_draft") or item.get("draft") or item.get("raw_agent_draft") or ""
    source = item.get("source") or {}
    action_type = item.get("action_type") or item.get("type")
    channel = item.get("channel", "")
    risk = classify_action(channel, action_type, draft, source)
    claim_level, claim_tags = check_claims(draft)
    tags = list(dict.fromkeys([*risk.get("reasons", []), *claim_tags]))

    if claim_level == "block" or item.get("risk_level") == "block":
        revised = _minimal_legal_revision(draft)
        if revised != draft:
            return {
                "agent": "Legal",
                "decision": "require_changes",
                "changed": True,
                "risk_tags": tags,
                "rationale": "Clear claim-boundary issue found; proposed a minimal wording correction.",
                "revised_draft": revised,
            }
        return {
            "agent": "Legal",
            "decision": "block",
            "changed": False,
            "risk_tags": tags,
            "rationale": "Clear legal or policy risk remains and cannot be safely corrected automatically.",
            "revised_draft": "",
        }

    if any(tag.startswith("escalation_category:") for tag in tags):
        return {
            "agent": "Legal",
            "decision": "pass",
            "changed": False,
            "risk_tags": tags,
            "rationale": "No wording change needed; retain human review for this category before sending.",
            "revised_draft": "",
        }

    if "possible_private_or_decision_pack_content" in tags:
        revised = _remove_private_boundary_terms(draft)
        return {
            "agent": "Legal",
            "decision": "recommend_changes" if revised != draft else "block",
            "changed": revised != draft,
            "risk_tags": tags,
            "rationale": "Possible private or decision-pack wording detected; public draft should avoid those terms.",
            "revised_draft": revised if revised != draft else "",
        }

    return {
        "agent": "Legal",
        "decision": "pass",
        "changed": False,
        "risk_tags": tags,
        "rationale": "No clear legal or material wording issue found. No change recommended.",
        "revised_draft": "",
    }


def _minimal_legal_revision(text: str) -> str:
    replacements = [
        (r"(?i)\bDIIaC\b\s+certif(?:y|ies|ied|ication)\s+compliance", "DIIaC supports evidence-bound governance review"),
        (r"(?i)\bDIIaC\b\s+guarantees compliance", "DIIaC supports evidence-bound governance review"),
        (r"(?i)(?:M2|M-Squared)\s+proves\s+truth", "M2 reviews structure, salience, and divergence signals"),
        (r"(?i)(?:M2|M-Squared)\s+certifies\s+truth", "M2 reviews structure, salience, and divergence signals"),
        (r"(?i)(?:M2|M-Squared)\s+knows\s+model\s+intent", "M2 reviews observable reasoning artefacts and divergence signals"),
        (r"(?i)(?:DIIaC|M2|M-Squared)\s+autonomously\s+approves", "DIIaC supports human accountable review"),
        (r"(?i)(?:DIIaC|M2|M-Squared)\s+overrides", "DIIaC and M2 support"),
        (r"(?i)replaces systems of record", "integrates with governed records and review processes"),
    ]
    revised = text
    for pattern, replacement in replacements:
        revised = re.sub(pattern, replacement, revised)
    return revised


def _remove_private_boundary_terms(text: str) -> str:
    revised = re.sub(r"(?i)\bconfidential\b", "non-public", text)
    revised = re.sub(r"(?i)\bprivate customer\b", "customer", revised)
    revised = re.sub(r"(?i)\bsigned pack\b", "governed artefact", revised)
    revised = re.sub(r"(?i)\bdecision pack\b", "decision artefact", revised)
    return revised
