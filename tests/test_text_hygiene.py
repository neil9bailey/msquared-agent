from msquared_agent.action_router import action_summary
from msquared_agent.text_hygiene import NON_LATIN_OMITTED, display_excerpt, product_excerpt


MIXED_SCRIPT_X_TEXT = (
    "\u0e01\u0e23\u0e30\u0e41\u0e2a autonomous AI coding "
    "\u0e01\u0e33\u0e25\u0e31\u0e07\u0e1e\u0e32 software engineering "
    "\u0628\u0650\u0633\u0652\u0645\u0650 \u0627\u0644\u0644\u0647\u0650 "
    "\u0627\u0644\u0631\u064e\u0651\u062d\u0652\u0645\u0670\u0646\u0650 "
    "\u0627\u0644\u0631\u064e\u0651\u062d\u0650\u064a\u0652\u0645\n\n"
    "AN INSTITUTIONAL WARNING TO UNALIGNED STATES\n"
    "DIIaC\u2122 + M\u00b2\n"
    "Human\u2013Machine Symbiosis for AI Governance\n"
    "M Squared makes the reasoning signals reviewable."
)


def test_product_excerpt_prefers_relevant_product_text_over_mixed_script_preamble():
    excerpt = product_excerpt(MIXED_SCRIPT_X_TEXT, limit=180)

    assert "DIIaC" in excerpt
    assert "M2" in excerpt
    assert "Human-Machine" in excerpt
    assert "\u0e01" not in excerpt
    assert "\u0628" not in excerpt


def test_display_excerpt_omits_non_latin_runs():
    excerpt = display_excerpt(MIXED_SCRIPT_X_TEXT, limit=120)

    assert NON_LATIN_OMITTED in excerpt
    assert "\u0e01" not in excerpt
    assert "\u0628" not in excerpt


def test_action_summary_notes_mixed_non_latin_text_but_preserves_product_summary():
    summary = action_summary({
        "id": "in_1",
        "canonical_id": "MSQ-X-20260614-0006",
        "channel": "x",
        "source_type": "x_monitor",
        "text": MIXED_SCRIPT_X_TEXT,
    })

    assert "Summary: DIIaC" in summary
    assert "mixed non-Latin text was omitted" in summary
    assert "\u0e01" not in summary
    assert "\u0628" not in summary
