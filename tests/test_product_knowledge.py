from pathlib import Path

from msquared_agent.product_knowledge import (
    build_product_knowledge_index,
    build_validation_packet,
    search_product_knowledge,
)


def test_product_knowledge_indexes_public_and_internal_without_secrets(tmp_path):
    diiac = tmp_path / "itservices.diiac.io"
    public_docs = diiac / "docs" / "public"
    internal_docs = diiac / "docs" / "architecture"
    public_docs.mkdir(parents=True)
    internal_docs.mkdir(parents=True)
    (public_docs / "showcase.md").write_text(
        "# DIIaC Showcase\nDIIaC creates evidence-bound signed decision packs for IT service transition.",
        encoding="utf-8",
    )
    (internal_docs / "architecture.md").write_text(
        "# Internal Architecture\nThe runtime applies policy-pack hard gates and Merkle verification.",
        encoding="utf-8",
    )
    (diiac / ".env").write_text("OPENAI_API_KEY=secret", encoding="utf-8")

    status = build_product_knowledge_index([diiac])
    public_results = search_product_knowledge("signed decision packs", mode="public_safe")
    technical_results = search_product_knowledge("Merkle policy hard gates", mode="technical_local")

    assert status["document_count"] == 2
    assert status["sensitivity_counts"]["public_safe"] == 1
    assert status["sensitivity_counts"]["internal"] == 1
    assert all(result["sensitivity"] == "public_safe" for result in public_results)
    assert any(result["sensitivity"] == "internal" for result in technical_results)
    assert "secret" not in build_validation_packet("OPENAI key", mode="technical_local")


def test_validation_packet_contains_source_paths(tmp_path):
    m2 = tmp_path / "M-Squared-Architecture"
    m2.mkdir()
    source = m2 / "README.md"
    source.write_text(
        "# M2\nM2 provides advisory interpretability signals for governed decision cases.",
        encoding="utf-8",
    )
    build_product_knowledge_index([m2])

    packet = build_validation_packet("advisory interpretability", mode="technical_local")

    assert "MSquared Product Validation Packet" in packet
    assert str(source) in packet
    assert "advisory interpretability" in packet
