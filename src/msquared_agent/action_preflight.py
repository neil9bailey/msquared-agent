from .app_log import log_event
from .approval_queue import get_approval_item, update_approval_item
from .connector_config import connector_status
from .email_adapter import prepare_email_payload
from .x_adapter import prepare_x_payload


def run_action_preflight(item_id: str) -> dict:
    item = get_approval_item(item_id)
    if not item:
        raise ValueError(f"Approval item not found: {item_id}")

    log_event(
        "action_preflight_started",
        "info",
        "Final Action Agent preflight started.",
        {"approval_item_id": item_id, "channel": item.get("channel"), "action_type": item.get("action_type") or item.get("type")},
    )
    result = _preflight_item(item)
    updates = {
        "preflight": result,
        "pipeline_state": "action_preflight_passed" if result["decision"] == "pass" else "action_preflight_blocked",
    }
    update_approval_item(item_id, updates)
    log_event(
        "action_preflight_passed" if result["decision"] == "pass" else "action_preflight_blocked",
        "info" if result["decision"] == "pass" else "warning",
        "Final Action Agent preflight completed.",
        {
            "approval_item_id": item_id,
            "decision": result["decision"],
            "action": result.get("action"),
            "checks": result.get("checks", []),
        },
    )
    return result


def _preflight_item(item: dict) -> dict:
    checks = []
    if item.get("status") != "approved":
        return _blocked("Draft must be human-approved before preflight.", checks, item)
    if item.get("risk_level") == "block":
        return _blocked("Blocked drafts cannot be prepared for live action.", checks, item)
    legal = item.get("legal_review") or {}
    if legal.get("decision") == "block":
        return _blocked("Legal Agent blocked this draft.", checks, item)

    status = connector_status()
    if item.get("channel") == "x":
        action = "x_reply" if item.get("type") == "x_reply" else "new_x_post"
        source = item.get("source") or {}
        reply_to = item.get("reply_to") or item.get("external_source_id") or source.get("source_id")
        if item.get("type") == "x_reply" and not reply_to:
            return _blocked("X replies require a source tweet id.", checks, item, action)
        payload = prepare_x_payload(item["id"])
        checks.append({"name": "payload", "ok": True, "endpoint": payload.get("endpoint")})
        checks.append({"name": "connector_ready", "ok": bool(status["x"]["ready_to_write"]), "auth_mode": status["x"].get("write_auth_mode")})
        if not status["x"]["ready_to_write"]:
            return _blocked(_x_write_not_ready_message(status["x"]), checks, item, action, payload)
        return {
            "decision": "pass",
            "action": action,
            "message": "X action is ready for final operator confirmation.",
            "target": reply_to if action == "x_reply" else "MSquared X account",
            "checks": checks,
            "payload": payload,
        }

    if item.get("channel") == "email":
        payload = prepare_email_payload(item["id"])
        checks.append({"name": "payload", "ok": True, "recipient": payload.get("to")})
        checks.append({"name": "connector_ready", "ok": bool(status["email"]["ready_to_send"])})
        if not status["email"]["ready_to_send"]:
            return _blocked("Email payload is valid, but SMTP send readiness is incomplete. Enable email send and check SMTP settings.", checks, item, "email_send", payload)
        return {
            "decision": "pass",
            "action": "email_send",
            "message": "Email action is ready for final operator confirmation.",
            "target": payload.get("to"),
            "checks": checks,
            "payload": payload,
        }

    return _blocked("Unsupported channel for final action.", checks, item)


def _x_write_not_ready_message(status: dict) -> str:
    warning = status.get("write_setup_warning") or ""
    if status.get("write_auth_mode") == "oauth1a_user_unverified":
        return (
            "X payload is valid, but posting is not armed because only OAuth 1.0a credentials are configured. "
            "Use Admin -> Generate OAuth 2 Tokens so X_OAUTH2_ACCESS_TOKEN and X_OAUTH2_REFRESH_TOKEN are saved. "
            f"{warning}"
        ).strip()
    if not status.get("write_enabled"):
        return "X payload is valid, but ENABLE_X_WRITE is disabled. Enable X write only when you are ready for live posting."
    return f"X payload is valid, but X write readiness is incomplete. {warning}".strip()


def _blocked(message: str, checks: list[dict], item: dict, action: str = "", payload: dict | None = None) -> dict:
    checks.append({"name": "blocked", "ok": False, "message": message})
    return {
        "decision": "blocked",
        "action": action or item.get("action_type") or item.get("type", ""),
        "message": message,
        "target": "",
        "checks": checks,
        "payload": payload or {},
    }
