from .persona import PERSONA
from .content_planner import draft_email_response, draft_x_post, draft_x_reply, summarize_source_for_post
from .approval_queue import add_to_queue
from .app_log import log_event
from .audit_store import log_action
from .paths import resource_path
from .risk_classifier import classify_action


CHANNEL_BY_TYPE = {
    "x_post": "x",
    "x_reply": "x",
    "x_dm": "x",
    "email": "email",
    "email_response": "email",
}


def generate_draft(content_type: str, input_text: str = "", context: dict = None) -> dict:
    if context is None:
        context = {}

    # Load system prompt
    prompt_path = resource_path("prompts", "MSQUARED_SYSTEM_PROMPT.md")
    with open(prompt_path, encoding="utf-8") as f:
        system_prompt = f.read()

    source = context.get("source") or {}
    draft_override = (context.get("draft_override") or "").strip()
    if draft_override:
        draft_text = draft_override
    elif content_type == "x_post":
        topic = input_text or summarize_source_for_post(source)
        draft_text = draft_x_post(topic, context)
    elif content_type == "x_reply":
        source = source or {"text": input_text, "source_type": context.get("source_type", "manual_x_reply")}
        draft_text = draft_x_reply(source)
    elif content_type in {"email", "email_response"}:
        source = source or {"subject": context.get("subject", "Inquiry"), "text": input_text}
        draft_text = draft_email_response(source)
    else:
        draft_text = input_text

    channel = CHANNEL_BY_TYPE.get(content_type, "manual")
    risk = classify_action(channel, content_type, draft_text, source)
    status = "needs_review" if risk["level"] in {"medium", "high", "block"} else "drafted"
    item = {
        "type": content_type,
        "channel": channel,
        "draft": draft_text,
        "risk_level": risk["level"],
        "risks": risk["reasons"],
        "claims_checked": risk["claims_checked"],
        "category": risk.get("category"),
        "context": context,
        "source": source,
        "persona": PERSONA["name"],
        "status": status,
        "system_prompt": system_prompt[:120],
    }

    queued_item = add_to_queue(item)
    log_action({
        "action": "draft_generated",
        "approval_item_id": queued_item["id"],
        "channel": channel,
        "type": content_type,
        "source_item": source.get("id") or source.get("source_id"),
        "draft_text": draft_text,
        "risk_result": risk,
        "claims_checked": risk["claims_checked"],
        "approver": None,
        "final_action_status": "drafted",
        "draft_preview": draft_text[:200]
    })
    log_event(
        "draft_generated",
        "info",
        "Draft generated and added to approval queue.",
        {
            "approval_item_id": queued_item["id"],
            "channel": channel,
            "type": content_type,
            "risk_level": risk["level"],
            "source_item": source.get("id") or source.get("source_id"),
        },
    )

    return queued_item

def main():
    print("MSquared Agent - Phase 0 Draft Mode")
    print("Human approval required for all actions.")
