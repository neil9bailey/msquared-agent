import email
import imaplib
import smtplib
from email import policy
from email.utils import parseaddr
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone

from .app_log import log_event
from .approval_queue import add_to_queue
from .approval_queue import get_approval_item, mark_sent_or_posted
from .audit_store import log_action
from .claim_guard import check_claims
from .env_loader import get_env, load_env_file
from .intake_store import add_intake_item
from .opt_out_registry import is_opted_out
from .settings import feature_enabled


def fetch_inbound_emails(config: dict | None = None):
    """Fetch website/contact emails into the intake store.

    With ENABLE_EMAIL_READ=false this only imports operator-supplied local items.
    """
    config = config or {}
    load_env_file()
    items = []
    log_event(
        "email_fetch_started",
        "info",
        "Email refresh started.",
        {"local_item_count": len(config.get("items", []))},
    )
    for item in config.get("items", []):
        items.append(add_intake_item({
            "channel": "email",
            "source_type": item.get("source_type", "website_contact"),
            "source_id": item.get("id") or item.get("source_id"),
            "from": item.get("from", ""),
            "subject": item.get("subject", ""),
            "text": item.get("text") or item.get("body", ""),
        }))

    if not feature_enabled("ENABLE_EMAIL_READ"):
        log_event(
            "email_fetch_skipped",
            "info",
            "Email read is disabled. Imported local/operator-supplied items only.",
            {"imported_count": len(items), "reason": "ENABLE_EMAIL_READ=false"},
        )
        return items

    try:
        imap_server = config.get("imap_server") or get_env("EMAIL_IMAP_SERVER")
        imap_port = _int_setting(config.get("imap_port") or get_env("EMAIL_IMAP_PORT", "993"), 993)
        imap_security = config.get("imap_security") or get_env("EMAIL_IMAP_SECURITY", "SSL/TLS")
        email_address = config.get("email") or get_env("EMAIL_ADDRESS")
        password = config.get("password") or get_env("EMAIL_PASSWORD")
        if not all([imap_server, email_address, password]):
            log_event(
                "email_fetch_skipped",
                "warning",
                "Email read is enabled but IMAP credentials are missing.",
                {"imported_count": len(items), "reason": "IMAP credentials missing"},
            )
            log_action({
                "action": "email_fetch_skipped",
                "channel": "email",
                "final_action_status": "skipped",
                "reason": "IMAP credentials missing",
            })
            return items

        mail = _connect_imap(imap_server, imap_port, imap_security)
        try:
            mail.login(email_address, password)
            mail.select(config.get("mailbox") or get_env("EMAIL_MAILBOX", "inbox"), readonly=True)
            status, messages = mail.search(None, 'UNSEEN')
            if status != "OK":
                log_event(
                    "email_fetch_failed",
                    "warning",
                    "IMAP search did not return OK.",
                    {"status": status, "imported_count": len(items)},
                )
                return items
            max_messages = int(config.get("max_messages", 25))
            fetched_count = 0
            for message_id in messages[0].split()[:max_messages]:
                status, data = mail.fetch(message_id, "(BODY.PEEK[])")
                if status != "OK" or not data:
                    continue
                parsed = email.message_from_bytes(data[0][1], policy=policy.default)
                body = _extract_body(parsed)
                items.append(add_intake_item({
                    "channel": "email",
                    "source_type": "website_contact",
                    "source_id": parsed.get("Message-ID") or message_id.decode("utf-8", errors="ignore"),
                    "from": parsed.get("From", ""),
                    "subject": parsed.get("Subject", ""),
                    "text": body,
                    "received_at": parsed.get("Date"),
                }))
                fetched_count += 1
            log_event(
                "email_fetch_complete",
                "info",
                "Email refresh completed.",
                {"imported_count": len(items), "fetched_count": fetched_count, "imap_server": imap_server, "imap_port": imap_port, "imap_security": imap_security},
            )
        finally:
            try:
                mail.logout()
            except Exception:
                pass
    except Exception as exc:
        log_event(
            "email_fetch_failed",
            "error",
            "Email refresh failed. Check IMAP host, port, security mode, mailbox, email address, and mailbox-specific password.",
            {"error": str(exc), "imported_count": len(items)},
        )
        log_action({
            "action": "email_fetch_failed",
            "channel": "email",
            "final_action_status": "failed",
            "error": str(exc),
        })
    return items


def _extract_body(message) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                return part.get_content()
        return ""
    return message.get_content()

def create_email_draft(to: str, subject: str, body: str, config: dict):
    risk_level, risks = check_claims(body)
    item = {
        "type": "email_response",
        "channel": "email",
        "to": to,
        "subject": subject,
        "draft": body,
        "risk_level": risk_level,
        "risks": risks,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    add_to_queue(item)
    log_action({"action": "email_draft", "to": to, "risk": risk_level})
    log_event("email_draft_created", "info", "Email draft created.", {"risk_level": risk_level, "recipient_configured": bool(to)})
    return item


def prepare_email_payload(item_id: str) -> dict:
    item = get_approval_item(item_id)
    if not item:
        raise ValueError(f"Approval item not found: {item_id}")
    if item.get("channel") != "email":
        raise ValueError("Approval item is not an email draft.")
    if item.get("status") != "approved":
        raise PermissionError("Email payloads can only be prepared after approval.")
    if item.get("risk_level") == "block":
        raise PermissionError("Blocked email items cannot be prepared.")

    source = item.get("source", {})
    recipient = item.get("to") or source.get("from") or item.get("context", {}).get("to")
    recipient = parseaddr(recipient or "")[1]
    if not recipient:
        raise ValueError("Email payload requires a recipient address.")
    if is_opted_out(recipient, "email"):
        raise PermissionError(f"{recipient} has opted out of email automation.")

    draft = item.get("draft", "")
    subject = item.get("subject") or source.get("subject") or "DIIaC inquiry"
    body = draft
    if draft.lower().startswith("subject:"):
        first_line, _, rest = draft.partition("\n")
        subject = first_line.replace("Subject:", "", 1).strip()
        body = rest.strip()

    result = {
        "to": recipient,
        "subject": subject,
        "body": body,
        "metadata": {"approval_item_id": item_id, "made_with_ai": True},
    }
    log_event("email_payload_prepared", "info", "Email payload prepared after approval.", {"approval_item_id": item_id, "recipient": recipient})
    return result


def send_approved_email(item_id: str, config: dict | None = None):
    payload = prepare_email_payload(item_id)
    if not feature_enabled("ENABLE_EMAIL_SEND"):
        log_event(
            "email_send_skipped",
            "info",
            "Email send is disabled; payload was not sent.",
            {"approval_item_id": item_id, "reason": "ENABLE_EMAIL_SEND=false"},
        )
        log_action({
            "action": "email_send_blocked_by_feature_flag",
            "approval_item_id": item_id,
            "channel": "email",
            "final_action_status": "not_sent",
        })
        return {"sent": False, "reason": "ENABLE_EMAIL_SEND=false", "payload": payload}

    smtp_config = config or {}
    load_env_file()
    message = MIMEMultipart()
    message["From"] = smtp_config.get("email") or get_env("EMAIL_ADDRESS")
    message["To"] = payload["to"]
    message["Subject"] = payload["subject"]
    message.attach(MIMEText(payload["body"], "plain"))

    smtp_server = smtp_config.get("smtp_server") or get_env("EMAIL_SMTP_SERVER")
    smtp_port = _int_setting(smtp_config.get("smtp_port") or get_env("EMAIL_SMTP_PORT", "587"), 587)
    smtp_security = smtp_config.get("smtp_security") or get_env("EMAIL_SMTP_SECURITY", "STARTTLS")
    email_address = smtp_config.get("email") or get_env("EMAIL_ADDRESS")
    password = smtp_config.get("password") or get_env("EMAIL_PASSWORD")
    if not all([smtp_server, email_address, password]):
        log_event(
            "email_send_failed",
            "error",
            "SMTP credentials are missing.",
            {"approval_item_id": item_id},
        )
        raise RuntimeError("SMTP credentials are missing.")

    try:
        _send_smtp_message(smtp_server, smtp_port, smtp_security, email_address, password, message)
    except Exception as exc:
        log_event(
            "email_send_failed",
            "error",
            "Approved email failed to send.",
            {"approval_item_id": item_id, "error": str(exc), "smtp_server": smtp_server, "smtp_port": smtp_port, "smtp_security": smtp_security},
        )
        log_action({
            "action": "email_send_failed",
            "approval_item_id": item_id,
            "channel": "email",
            "final_action_status": "failed",
            "error": str(exc),
        })
        raise

    mark_sent_or_posted(item_id)
    log_event("email_send_complete", "info", "Approved email sent.", {"approval_item_id": item_id, "recipient": payload["to"]})
    log_action({
        "action": "email_sent",
        "approval_item_id": item_id,
        "channel": "email",
        "final_action_status": "sent_or_posted",
    })
    return {"sent": True, "payload": payload}


def _int_setting(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_security(value: str | None) -> str:
    return (value or "").strip().lower().replace("_", " ").replace("-", " ")


def _uses_starttls(security: str | None) -> bool:
    return "starttls" in _normalize_security(security)


def _uses_implicit_tls(security: str | None) -> bool:
    normalized = _normalize_security(security)
    return "ssl" in normalized or "implicit tls" in normalized or normalized == "tls"


def _connect_imap(server: str, port: int, security: str):
    if _uses_implicit_tls(security):
        return imaplib.IMAP4_SSL(server, port)
    connection = imaplib.IMAP4(server, port)
    if _uses_starttls(security):
        connection.starttls()
    return connection


def _send_smtp_message(server: str, port: int, security: str, email_address: str, password: str, message):
    if _uses_implicit_tls(security):
        with smtplib.SMTP_SSL(server, port, timeout=30) as smtp:
            smtp.login(email_address, password)
            smtp.send_message(message)
        return

    with smtplib.SMTP(server, port, timeout=30) as smtp:
        smtp.ehlo()
        if _uses_starttls(security):
            smtp.starttls()
            smtp.ehlo()
        smtp.login(email_address, password)
        smtp.send_message(message)
