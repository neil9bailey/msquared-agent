import requests

from msquared_agent.interactive_agent import agent_status, ask_agent, create_agent_draft
from msquared_agent.approval_queue import list_queue
from msquared_agent.product_knowledge import build_product_knowledge_index


def test_agent_uses_local_fallback_without_openai_key(monkeypatch):
    def fail_post(*args, **kwargs):
        raise AssertionError("Local fallback should not call OpenAI")

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setattr("msquared_agent.interactive_agent.requests.post", fail_post)

    result = ask_agent(
        "summarize the selected email",
        {
            "selected": {
                "kind": "intake",
                "item": {
                    "id": "in_1",
                    "channel": "email",
                    "subject": "Can I book a demo?",
                    "text": "We would like a walkthrough.",
                },
            }
        },
    )

    assert result["mode"] == "local"
    assert "Likely category: demo request" in result["answer"]
    assert agent_status()["mode"] == "local"


def test_agent_uses_openai_responses_when_key_is_configured(monkeypatch):
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "output": [
                    {
                        "content": [
                            {"type": "output_text", "text": "Draft with approval boundary intact."}
                        ]
                    }
                ]
            }

    def fake_post(url, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    monkeypatch.setattr("msquared_agent.interactive_agent.requests.post", fake_post)

    result = ask_agent("shape an X post", {"selected": {"kind": "intake", "item": {"channel": "x", "text": "Governed AI"}}})

    assert result == {"answer": "Draft with approval boundary intact.", "mode": "openai", "model": "gpt-test"}
    assert len(calls) == 1
    assert calls[0]["headers"]["Authorization"] == "Bearer sk-test-secret"
    assert calls[0]["json"]["model"] == "gpt-test"
    assert "approval queue" in calls[0]["json"]["instructions"]
    assert "DIIaC is the governed decision assurance infrastructure" in calls[0]["json"]["instructions"]
    assert "M2 is the advisory interpretability and evaluation layer" in calls[0]["json"]["instructions"]
    assert "Governed AI" in calls[0]["json"]["input"]


def test_agent_draft_creation_adds_to_approval_queue():
    item = create_agent_draft("x_post", "Evidence-bound AI governance matters.", {})

    assert item["id"]
    assert item["channel"] == "x"
    assert item["status"] in {"drafted", "needs_review"}
    assert any(queued["id"] == item["id"] for queued in list_queue())


def test_openai_answer_failure_uses_local_fallback(monkeypatch):
    class ForbiddenResponse:
        status_code = 403
        text = ""

        def json(self):
            return {
                "error": {
                    "message": "Project is not allowed to use the requested model.",
                    "type": "permission_error",
                    "code": "model_not_allowed",
                }
            }

        def raise_for_status(self):
            error = requests.HTTPError("403 Client Error")
            error.response = self
            raise error

    def fake_post(url, headers, json, timeout):
        return ForbiddenResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-denied")
    monkeypatch.setattr("msquared_agent.interactive_agent.requests.post", fake_post)

    result = ask_agent("shape an X post", {"selected": {"kind": "intake", "item": {"channel": "x", "text": "Governed AI"}}})

    assert result["mode"] == "openai_fallback"
    assert result["model"] == "gpt-denied"
    assert "OpenAI forbade access" in result["openai_error"]
    assert "HTTP 403" in result["openai_error"]
    assert "For X" in result["answer"]


def test_openai_draft_failure_still_creates_approval_draft(monkeypatch):
    class ForbiddenResponse:
        status_code = 403
        text = ""

        def json(self):
            return {
                "error": {
                    "message": "Project is not allowed to use the requested model.",
                    "type": "permission_error",
                    "code": "model_not_allowed",
                }
            }

        def raise_for_status(self):
            error = requests.HTTPError("403 Client Error")
            error.response = self
            raise error

    def fake_post(url, headers, json, timeout):
        return ForbiddenResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-denied")
    monkeypatch.setattr("msquared_agent.interactive_agent.requests.post", fake_post)

    item = create_agent_draft("x_post", "Explain governed decision assurance.", {})

    assert item["id"]
    assert item["context"]["agent_mode"] == "local_fallback"
    assert "OpenAI forbade access" in item["context"]["agent_openai_error"]
    assert item["context"]["agent_openai_status_code"] == 403
    assert item["status"] in {"drafted", "needs_review"}
    assert any(queued["id"] == item["id"] for queued in list_queue())


def test_openai_agent_draft_uses_product_context_and_queue(monkeypatch):
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": "DIIaC governs the decision artifact. M2 reviews the signals. Humans stay accountable.",
                            }
                        ]
                    }
                ]
            }

    def fake_post(url, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    monkeypatch.setattr("msquared_agent.interactive_agent.requests.post", fake_post)

    item = create_agent_draft("x_post", "Explain DIIaC and M2 together.", {})

    assert item["draft"] == "DIIaC governs the decision artifact. M2 reviews the signals. Humans stay accountable."
    assert item["context"]["agent_mode"] == "openai"
    assert calls[0]["json"]["model"] == "gpt-test"
    assert "Return only the draft text" in calls[0]["json"]["input"]
    assert "DIIaC is the governed decision assurance infrastructure" in calls[0]["json"]["instructions"]


def test_technical_local_mode_does_not_send_internal_context_to_openai(monkeypatch, tmp_path):
    root = tmp_path / "itservices.diiac.io"
    docs = root / "docs" / "architecture"
    docs.mkdir(parents=True)
    (docs / "architecture.md").write_text(
        "# Internal Architecture\nDIIaC runtime hard gates verify evidence registers before final reliance.",
        encoding="utf-8",
    )
    build_product_knowledge_index([root])

    def fail_post(*args, **kwargs):
        raise AssertionError("technical_local must not call OpenAI")

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    monkeypatch.setenv("ALLOW_OPENAI_TECHNICAL_CONTEXT", "false")
    monkeypatch.setattr("msquared_agent.interactive_agent.requests.post", fail_post)

    result = ask_agent("How do hard gates verify evidence registers?", {"knowledge_mode": "technical_local"})

    assert result["mode"] == "technical_local"
    assert "Internal technical context was kept local" in result["answer"]
    assert "evidence registers" in result["answer"]


def test_technical_openai_requires_explicit_gate(monkeypatch, tmp_path):
    root = tmp_path / "itservices.diiac.io"
    docs = root / "docs" / "architecture"
    docs.mkdir(parents=True)
    (docs / "architecture.md").write_text(
        "# Internal Architecture\nDIIaC uses Merkle verification in the decision pack replay path.",
        encoding="utf-8",
    )
    build_product_knowledge_index([root])
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"output": [{"content": [{"type": "output_text", "text": "Technical answer."}]}]}

    def fake_post(url, headers, json, timeout):
        calls.append(json)
        return FakeResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    monkeypatch.setenv("ALLOW_OPENAI_TECHNICAL_CONTEXT", "true")
    monkeypatch.setattr("msquared_agent.interactive_agent.requests.post", fake_post)

    result = ask_agent("Explain Merkle verification", {"knowledge_mode": "technical_openai"})

    assert result["mode"] == "openai"
    assert calls
    assert "Merkle verification" in calls[0]["input"]
