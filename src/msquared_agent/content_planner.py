from .persona import PERSONA
from .risk_classifier import classify_email


def draft_x_post(topic: str = "", context: dict | None = None) -> str:
    context = context or {}
    topic = (topic or context.get("topic") or "").strip()
    if not topic:
        return (
            "A chatbot answer is not a governed decision.\n\n"
            "A governed decision needs frozen intent, evidence binding, policy controls, "
            "human review, signed artefacts, replayable audit, and independent verification.\n\n"
            "That is DIIaC. M2 adds the advisory lens on route behaviour, evidence salience, and divergence."
        )

    return (
        f"{topic}\n\n"
        "DIIaC governs the decision artefact: intent, evidence, controls, human review, "
        "signatures, ledger, replay, and verification.\n\n"
        "M2 is advisory. It reviews signals around model and route behaviour. Useful before promotional."
    )


def draft_x_reply(source: dict) -> str:
    text = (source.get("text") or "").strip()
    if "truth" in text.lower():
        return (
            "Useful question. MSquared does not certify truth or approve decisions.\n\n"
            "M2 reviews structure, salience, and divergence signals around a governed "
            "decision artefact. Humans remain accountable."
        )

    return (
        "Thanks for raising this. The short version: DIIaC governs the decision artefact, "
        "while M2 reviews advisory signals around structure, salience, and divergence.\n\n"
        "Review signal, not approval signal."
    )


def draft_email_response(source: dict) -> str:
    sender = source.get("from") or source.get("author") or "there"
    subject = source.get("subject") or "your note"
    body = source.get("text") or source.get("body") or ""
    category = classify_email(subject, body)
    greeting_name = sender.split("<")[0].strip().split()[0] if sender else "there"

    if category == "demo request":
        middle = (
            "Thanks for your interest in DIIaC. A useful demo usually starts with the "
            "decision workflow you want governed: intent, evidence, controls, review, "
            "sign-off, and audit replay."
        )
        next_step = "If helpful, send two or three lines on the use case and the decision owners involved."
    elif category == "partnership":
        middle = (
            "Thanks for reaching out. Partnerships make sense where governed decision "
            "artefacts, evidence binding, or independent verification need to connect into an existing workflow."
        )
        next_step = "Send the integration surface you have in mind and I can shape a first response for the team."
    elif category in {"legal/compliance", "security"}:
        middle = (
            "Thanks for the question. I can help route this, but legal, compliance, and "
            "security matters need human review before any substantive answer is sent."
        )
        next_step = "I will mark this for review and keep the response evidence-bound."
    elif category == "press/analyst":
        middle = (
            "Thanks for getting in touch. DIIaC is focused on governed decision intelligence: "
            "freezing intent, binding evidence, applying controls, and keeping human accountability explicit."
        )
        next_step = "Share the angle and deadline, and I can help prepare a concise briefing response."
    elif category == "spam/noise":
        middle = "Thanks for the message. This does not look like a fit for MSquared or DIIaC right now."
        next_step = "No further action is recommended unless a human reviewer decides otherwise."
    else:
        middle = (
            "Thanks for your note. DIIaC is building the governance layer for decision artefacts: "
            "intent, evidence, controls, human review, signatures, ledger, replay, and verification."
        )
        next_step = "Send a little more context and I can help route the request."

    return (
        f"Subject: Re: {subject}\n\n"
        f"Hi {greeting_name},\n\n"
        f"{middle}\n\n"
        f"{next_step}\n\n"
        f"Best,\n{PERSONA['name']}\nTransparent AI brand agent for DIIaC Ltd"
    )


def summarize_source_for_post(source: dict) -> str:
    channel = source.get("channel", "source")
    text = source.get("text") or source.get("body") or ""
    if len(text) > 220:
        text = text[:217].rstrip() + "..."
    return f"From {channel} intake: {text}"
