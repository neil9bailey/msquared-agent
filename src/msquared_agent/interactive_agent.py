import json
from typing import Any

import requests

from .agent import generate_draft
from .app_log import log_event
from .env_loader import DEFAULT_OPENAI_MODEL, env_bool, get_env, load_env_file, mask_secret
from .feedback_store import similar_approved_examples
from .paths import resource_path
from .product_knowledge import format_knowledge_context, search_product_knowledge
from .risk_classifier import classify_email
from .text_hygiene import display_excerpt, product_excerpt


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = DEFAULT_OPENAI_MODEL


def agent_status() -> dict:
    load_env_file()
    api_key = get_env("OPENAI_API_KEY")
    model = get_env("OPENAI_MODEL") or DEFAULT_MODEL
    return {
        "mode": "openai" if api_key else "local",
        "openai_configured": bool(api_key),
        "model": model,
        "masked_api_key": mask_secret(api_key),
    }


def ask_agent(prompt: str, context: dict | None = None, history: list[dict] | None = None) -> dict:
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("Ask MSquared something first.")

    load_env_file()
    context = context or {}
    history = history or []
    api_key = get_env("OPENAI_API_KEY")
    model = get_env("OPENAI_MODEL") or DEFAULT_MODEL
    knowledge_mode = context.get("knowledge_mode", "public_safe")
    technical_mode = knowledge_mode in {"technical_local", "technical_openai"}
    knowledge_results = search_product_knowledge(
        prompt,
        mode="technical_local" if technical_mode else "public_safe",
        limit=8 if technical_mode else 5,
    )
    context = dict(context)
    context["knowledge_results"] = knowledge_results

    allow_technical_openai = env_bool("ALLOW_OPENAI_TECHNICAL_CONTEXT", False)
    can_send_to_openai = bool(api_key) and (
        not technical_mode or knowledge_mode == "technical_openai" and allow_technical_openai
    )

    if can_send_to_openai:
        try:
            answer = _ask_openai(prompt, context, history, api_key, model)
            mode = "openai"
            openai_error = None
        except (requests.RequestException, RuntimeError) as exc:
            openai_error = _describe_openai_error(exc, model)
            log_event(
                "agent_openai_answer_fallback",
                "warning",
                "OpenAI answer failed; local governed fallback was used.",
                {
                    "model": model,
                    "status_code": _openai_status_code(exc),
                    "error": openai_error,
                    "knowledge_mode": knowledge_mode,
                    "context": _context_digest(context),
                    "knowledge_sources": _knowledge_source_digest(knowledge_results),
                },
            )
            answer = _local_agent_answer(prompt, context)
            mode = "openai_fallback"
    else:
        answer = _local_agent_answer(prompt, context)
        mode = "technical_local" if technical_mode else "local"
        openai_error = None

    log_event(
        "agent_answered",
        "info",
        "Interactive MSquared agent answered an operator prompt.",
        {
            "mode": mode,
            "model": model,
            "prompt": prompt,
            "context": _context_digest(context),
            "knowledge_mode": knowledge_mode,
            "knowledge_sources": _knowledge_source_digest(knowledge_results),
        },
    )
    result = {"answer": answer, "mode": mode, "model": model}
    if openai_error:
        result["openai_error"] = openai_error
    return result


def create_agent_draft(content_type: str, prompt: str, context: dict | None = None) -> dict:
    context = context or {}
    load_env_file()
    draft_context = dict(context)
    api_key = get_env("OPENAI_API_KEY")
    model = get_env("OPENAI_MODEL") or DEFAULT_MODEL
    mode = "local"
    openai_error = None
    public_results = search_product_knowledge(prompt, mode="public_safe", limit=5)
    similar_examples = similar_approved_examples(prompt, action_type=content_type, limit=3)
    draft_context["knowledge_results"] = public_results
    draft_context["similar_examples"] = similar_examples
    if api_key:
        try:
            draft_context["draft_override"] = _draft_with_openai(content_type, prompt, draft_context, api_key, model)
            draft_context["agent_mode"] = "openai"
            mode = "openai"
        except (requests.RequestException, RuntimeError) as exc:
            openai_error = _describe_openai_error(exc, model)
            draft_context["agent_mode"] = "local_fallback"
            draft_context["agent_openai_error"] = openai_error
            draft_context["agent_openai_status_code"] = _openai_status_code(exc)
            mode = "local_fallback"
            log_event(
                "agent_openai_draft_fallback",
                "warning",
                "OpenAI draft failed; local governed fallback draft was created instead.",
                {
                    "model": model,
                    "status_code": _openai_status_code(exc),
                    "error": openai_error,
                    "type": content_type,
                    "context": _context_digest(context),
                    "knowledge_sources": _knowledge_source_digest(public_results),
                },
            )
    else:
        draft_context["agent_mode"] = "local"
    item = generate_draft(content_type, prompt, draft_context)
    log_event(
        "agent_draft_created",
        "info",
        "Interactive MSquared agent created a draft for approval.",
        {
            "approval_item_id": item["id"],
            "type": item.get("type"),
            "channel": item.get("channel"),
            "risk_level": item.get("risk_level"),
            "mode": mode,
            "model": model,
            "openai_error": openai_error,
            "prompt": prompt,
            "context": _context_digest(context),
            "knowledge_sources": _knowledge_source_digest(draft_context.get("knowledge_results", [])),
            "similar_example_count": len(draft_context.get("similar_examples", [])),
        },
    )
    return item


def summarize_context(context: dict | None) -> str:
    context = context or {}
    selected = context.get("selected") or {}
    if not selected:
        return "No selected context."

    kind = selected.get("kind", "item")
    item = selected.get("item") or {}
    channel = item.get("channel", "")
    source = item.get("source_type") or item.get("type", "")
    subject = item.get("subject", "")
    author = item.get("from") or item.get("author") or item.get("to") or ""
    text = item.get("text") or item.get("body") or item.get("draft") or ""
    preview = product_excerpt(text, 180) if channel == "x" else display_excerpt(text, 180)

    parts = [f"{kind}: {item.get('id', 'unsaved')}"]
    if channel:
        parts.append(f"channel={channel}")
    if source:
        parts.append(f"source={source}")
    if author:
        parts.append(f"party={author}")
    if subject:
        parts.append(f"subject={subject}")
    if preview:
        parts.append(f"preview={preview}")
    return " | ".join(parts)


def _ask_openai(prompt: str, context: dict, history: list[dict], api_key: str, model: str) -> str:
    system_prompt = _system_prompt()
    operator_context = _render_context(context)
    knowledge_context = _render_knowledge_context(context)
    conversation = _render_history(history[-8:])
    user_input = (
        f"{conversation}\n\n"
        f"Selected operator context:\n{operator_context}\n\n"
        f"Retrieved product knowledge:\n{knowledge_context}\n\n"
        f"Operator request:\n{prompt}"
    ).strip()
    response = requests.post(
        OPENAI_RESPONSES_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "instructions": system_prompt,
            "input": user_input,
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    text = _extract_response_text(payload)
    if not text:
        raise RuntimeError("OpenAI response completed without text output.")
    return text.strip()


def _draft_with_openai(content_type: str, prompt: str, context: dict, api_key: str, model: str) -> str:
    format_rules = {
        "x_post": "Write one original X post. Keep it under 260 characters. No thread. No hashtags unless truly useful.",
        "x_reply": "Write one X reply to the selected X intake. Keep it under 260 characters. Do not reply to keyword-search or monitor-only items.",
        "email_response": "Write one email response. Include a Subject: line, greeting, concise body, and MSquared sign-off.",
    }.get(content_type, "Write one concise public-facing draft.")
    user_input = (
        f"Draft type: {content_type}\n"
        f"Format rules: {format_rules}\n\n"
        f"Selected operator context:\n{_render_context(context)}\n\n"
        f"Public-safe product knowledge:\n{_render_knowledge_context(context, public_only=True)}\n\n"
        f"Similar approved examples for local style guidance:\n{_render_similar_examples(context)}\n\n"
        f"Operator drafting instruction:\n{prompt}\n\n"
        "Return only the draft text. Do not explain your reasoning."
    )
    response = requests.post(
        OPENAI_RESPONSES_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "instructions": _system_prompt(),
            "input": user_input,
        },
        timeout=60,
    )
    response.raise_for_status()
    text = _extract_response_text(response.json()).strip()
    if not text:
        raise RuntimeError("OpenAI draft response completed without text output.")
    return text


def _extract_response_text(payload: dict[str, Any]) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"])

    chunks = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                chunks.append(str(content["text"]))
    return "\n".join(chunks)


def _describe_openai_error(exc: BaseException, model: str) -> str:
    status_code = _openai_status_code(exc)
    error_code = ""
    error_type = ""
    provider_message = ""
    response = getattr(exc, "response", None)
    if response is not None:
        try:
            payload = response.json()
            error = payload.get("error") or {}
            error_code = str(error.get("code") or "")
            error_type = str(error.get("type") or "")
            provider_message = _truncate(str(error.get("message") or ""), 240)
        except (ValueError, AttributeError):
            provider_message = _truncate(getattr(response, "text", "") or "", 240)

    if status_code == 401:
        message = "OpenAI rejected the API key. Check OPENAI_API_KEY and the selected project."
    elif status_code == 403:
        message = (
            f"OpenAI forbade access for model '{model}'. The key/project may not have permission for this model "
            "or for the Responses API."
        )
    elif status_code == 404:
        message = f"OpenAI could not find the configured model or endpoint for model '{model}'."
    elif status_code == 429:
        message = "OpenAI rate limit or quota was reached."
    elif status_code and status_code >= 500:
        message = "OpenAI service returned a server error."
    elif isinstance(exc, requests.Timeout):
        message = "OpenAI request timed out."
    elif isinstance(exc, requests.ConnectionError):
        message = "OpenAI network connection failed."
    elif isinstance(exc, requests.RequestException):
        message = "OpenAI request failed before a usable response was returned."
    else:
        message = str(exc) or "OpenAI response could not be used."

    details = []
    if status_code:
        details.append(f"HTTP {status_code}")
    if error_type:
        details.append(f"type={error_type}")
    if error_code:
        details.append(f"code={error_code}")
    if provider_message:
        details.append(f"provider={provider_message}")
    if details:
        message = f"{message} ({'; '.join(details)})"
    return message


def _openai_status_code(exc: BaseException) -> int | None:
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)


def _local_agent_answer(prompt: str, context: dict) -> str:
    selected = (context or {}).get("selected") or {}
    item = selected.get("item") or {}
    text = item.get("text") or item.get("body") or item.get("draft") or prompt
    subject = item.get("subject") or ""
    channel = item.get("channel") or "operator"
    category = classify_email(subject, text) if channel == "email" else ""
    knowledge_results = context.get("knowledge_results", [])
    knowledge_note = _local_knowledge_answer(prompt, knowledge_results)

    lower_prompt = prompt.lower()
    if "summary" in lower_prompt or "summarise" in lower_prompt or "summarize" in lower_prompt:
        return (
            f"Selected context: {summarize_context(context)}\n\n"
            f"Likely category: {category or 'brand / X conversation'}.\n"
            "Recommended next step: create a draft, review claim risk, then approve only if the response is evidence-bound.\n\n"
            f"{knowledge_note}"
        )
    if "risk" in lower_prompt or "guardrail" in lower_prompt or "approve" in lower_prompt:
        return (
            "Governance check: keep this draft useful before promotional, avoid compliance-certification language, "
            "avoid truth/proof claims for M2, and do not imply MSquared can approve decisions. "
            "Use the approval queue before any post or send action.\n\n"
            f"{knowledge_note}"
        )
    if "email" in lower_prompt:
        return (
            "For email, MSquared should acknowledge the request, classify the intent, ask for the minimum useful context, "
            "and explain DIIaC as governed decision assurance infrastructure with M2 as an advisory evaluation layer. "
            "Escalate legal, compliance, or security topics for human review.\n\n"
            f"{knowledge_note}"
        )
    if "x" in lower_prompt or "post" in lower_prompt or "reply" in lower_prompt:
        return (
            "For X, keep it concise: DIIaC governs the decision artifact; M2 is advisory and reviews route behaviour, "
            "governance salience, evidence salience, uncertainty, and divergence signals. Avoid duplicate or keyword-search auto-replies.\n\n"
            f"{knowledge_note}"
        )
    return (
        "I can help summarize selected intake, shape an X post/reply, draft an email response, or flag escalation points. "
        "Everything public-facing still goes through the approval queue.\n\n"
        f"{knowledge_note}"
    )


def _system_prompt() -> str:
    prompt_path = resource_path("prompts", "MSQUARED_SYSTEM_PROMPT.md")
    with open(prompt_path, encoding="utf-8") as file:
        base = file.read()
    product_context_path = resource_path("prompts", "MSQUARED_PRODUCT_CONTEXT.md")
    try:
        with open(product_context_path, encoding="utf-8") as file:
            product_context = file.read()
    except FileNotFoundError:
        product_context = ""
    return (
        f"{base}\n\n"
        f"{product_context}\n\n"
        "You are operating inside the MSquared desktop operator console. "
        "You may advise, summarize, classify, and draft only. "
        "Never say that you posted, sent, approved, certified, or completed a public action. "
        "When the operator asks for a public action, produce a draft or advise using the approval queue."
    )


def _render_history(history: list[dict]) -> str:
    if not history:
        return "Conversation so far: none."
    lines = ["Conversation so far:"]
    for message in history:
        role = message.get("role", "operator")
        content = _truncate(str(message.get("content", "")), 900)
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _render_context(context: dict) -> str:
    selected = context.get("selected") or {}
    if not selected:
        return "No selected intake or draft was included."
    item = selected.get("item") or {}
    safe = {
        "kind": selected.get("kind"),
        "id": item.get("id"),
        "channel": item.get("channel"),
        "source_type": item.get("source_type") or item.get("type"),
        "status": item.get("status"),
        "risk_level": item.get("risk_level"),
        "subject": item.get("subject"),
        "from": item.get("from") or item.get("author"),
        "to": item.get("to"),
        "text": _truncate(item.get("text") or item.get("body") or item.get("draft") or "", 5000),
    }
    return json.dumps(safe, indent=2, default=str)


def _render_knowledge_context(context: dict, public_only: bool = False) -> str:
    results = context.get("knowledge_results", [])
    include_internal = not public_only and context.get("knowledge_mode") == "technical_openai"
    return format_knowledge_context(results, include_internal=include_internal)


def _render_similar_examples(context: dict) -> str:
    examples = context.get("similar_examples", [])
    if not examples:
        return "No approved local examples matched this request."
    lines = []
    for index, example in enumerate(examples, start=1):
        text = _truncate(example.get("final_text", "").replace("\n", " "), 700)
        lines.append(
            f"[{index}] {example.get('action_type')} | draft={example.get('draft_id')} | "
            f"intake={example.get('intake_id')} | score={example.get('score')}: {text}"
        )
    return "\n".join(lines)


def _local_knowledge_answer(prompt: str, results: list[dict]) -> str:
    if not results:
        return "Product knowledge: no local indexed source matched this question. Use Refresh Product Knowledge, then ask again."
    lines = ["Local product knowledge matches:"]
    for index, item in enumerate(results[:6], start=1):
        excerpt = item.get("excerpt", "").replace("\n", " ")
        if len(excerpt) > 360:
            excerpt = excerpt[:357].rstrip() + "..."
        lines.append(
            f"{index}. {item.get('product')} | {item.get('title')} | "
            f"{item.get('relative_path')} | {item.get('sensitivity')}: {excerpt}"
        )
    if any(item.get("sensitivity") != "public_safe" for item in results):
        lines.append(
            "Internal technical context was kept local. Use Technical OpenAI mode only if you deliberately allow "
            "selected internal snippets to be sent to OpenAI."
        )
    return "\n".join(lines)


def _context_digest(context: dict) -> dict:
    selected = (context or {}).get("selected") or {}
    item = selected.get("item") or {}
    return {
        "kind": selected.get("kind"),
        "id": item.get("id"),
        "channel": item.get("channel"),
        "status": item.get("status"),
    }


def _knowledge_source_digest(results: list[dict]) -> list[dict]:
    return [
        {
            "product": item.get("product"),
            "relative_path": item.get("relative_path"),
            "sensitivity": item.get("sensitivity"),
            "score": item.get("score"),
        }
        for item in results[:8]
    ]


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."
