import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .env_loader import get_env
from .paths import writable_path


INDEX_FILE = writable_path("data", "product_knowledge_index.json")
DEFAULT_ROOTS = [
    r"F:\code\diiac\itservices.diiac.io",
    r"F:\code\M-Squared-Architecture",
]
ALLOWED_EXTENSIONS = {
    ".bicep",
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".ps1",
    ".py",
    ".txt",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}
SKIP_DIR_NAMES = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "artifacts",
    "audit_exports",
    "build",
    "dist",
    "exports",
    "local-runtime-backups",
    "node_modules",
    "output",
    "state",
    "tmp",
}
SKIP_FILE_PATTERNS = (
    ".env",
    ".pem",
    ".pfx",
    ".key",
    ".crt",
    ".zip",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".docx",
    ".xlsx",
    ".pdf",
)
MAX_FILE_BYTES = 1_500_000
MAX_CHUNK_CHARS = 2600
CHUNK_OVERLAP_CHARS = 250


def configured_roots() -> list[Path]:
    raw = get_env("PRODUCT_KNOWLEDGE_ROOTS", "") or ""
    values = [item.strip() for item in raw.split(";") if item.strip()] or DEFAULT_ROOTS
    roots = []
    for value in values:
        path = Path(value).expanduser()
        if path.exists() and path not in roots:
            roots.append(path)
    return roots


def build_product_knowledge_index(roots: list[str | Path] | None = None) -> dict:
    selected_roots = [Path(root).expanduser() for root in roots] if roots else configured_roots()
    documents = []
    skipped = {"missing_roots": 0, "oversize_files": 0, "unsupported_files": 0, "sensitive_files": 0}
    for root in selected_roots:
        if not root.exists():
            skipped["missing_roots"] += 1
            continue
        for path in _iter_source_files(root):
            try:
                if _is_restricted_path(path):
                    skipped["sensitive_files"] += 1
                    continue
                if path.stat().st_size > MAX_FILE_BYTES:
                    skipped["oversize_files"] += 1
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for chunk_index, chunk in enumerate(_chunk_text(text)):
                if not chunk.strip():
                    continue
                documents.append(_document_record(root, path, chunk, chunk_index))

    index = {
        "schema_version": "msquared_product_knowledge_index_v1",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "roots": [str(root) for root in selected_roots],
        "document_count": len(documents),
        "skipped": skipped,
        "documents": documents,
    }
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return knowledge_status(index)


def load_product_knowledge_index() -> dict:
    if not INDEX_FILE.exists():
        return {
            "schema_version": "msquared_product_knowledge_index_v1",
            "built_at": None,
            "roots": [str(root) for root in configured_roots()],
            "document_count": 0,
            "skipped": {},
            "documents": [],
        }
    return json.loads(INDEX_FILE.read_text(encoding="utf-8"))


def knowledge_status(index: dict | None = None) -> dict:
    index = index or load_product_knowledge_index()
    counts: dict[str, int] = {}
    for document in index.get("documents", []):
        sensitivity = document.get("sensitivity", "internal")
        counts[sensitivity] = counts.get(sensitivity, 0) + 1
    return {
        "index_path": str(INDEX_FILE),
        "built_at": index.get("built_at"),
        "roots": index.get("roots", []),
        "document_count": index.get("document_count", len(index.get("documents", []))),
        "sensitivity_counts": counts,
        "skipped": index.get("skipped", {}),
    }


def search_product_knowledge(query: str, mode: str = "public_safe", limit: int = 6) -> list[dict]:
    query_tokens = _tokens(query)
    if not query_tokens:
        return []
    allowed = _allowed_sensitivities(mode)
    scored = []
    for document in load_product_knowledge_index().get("documents", []):
        if document.get("sensitivity") not in allowed:
            continue
        score = _score_document(query_tokens, document)
        if score > 0:
            scored.append((score, document))
    scored.sort(key=lambda item: item[0], reverse=True)
    results = []
    for score, document in scored[:limit]:
        result = dict(document)
        result["score"] = round(score, 4)
        result.pop("tokens", None)
        results.append(result)
    return results


def format_knowledge_context(results: list[dict], include_internal: bool = False) -> str:
    if not results:
        return "No indexed product knowledge matched this request."
    lines = []
    for index, item in enumerate(results, start=1):
        sensitivity = item.get("sensitivity", "internal")
        if sensitivity != "public_safe" and not include_internal:
            continue
        lines.append(
            f"[{index}] {item.get('product')} | {item.get('title')} | "
            f"{item.get('relative_path')} | sensitivity={sensitivity}"
        )
        lines.append(item.get("excerpt", "").strip())
        lines.append("")
    return "\n".join(lines).strip() or "No public-safe indexed product knowledge matched this request."


def build_validation_packet(query: str, mode: str = "technical_local", limit: int = 8) -> str:
    results = search_product_knowledge(query, mode=mode, limit=limit)
    lines = [
        "# MSquared Product Validation Packet",
        "",
        "Use this in Codex/Coding Chat to validate the MSquared Agent answer against local product sources.",
        "",
        f"Operator question: {query.strip() or '(no question supplied)'}",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Retrieved Sources",
        "",
    ]
    if not results:
        lines.append("No matching indexed sources. Refresh product knowledge and try again.")
    for index, item in enumerate(results, start=1):
        lines.extend([
            f"### Source {index}: {item.get('title')}",
            "",
            f"- Product: {item.get('product')}",
            f"- Sensitivity: {item.get('sensitivity')}",
            f"- Path: {item.get('path')}",
            "",
            "```text",
            item.get("excerpt", "").strip(),
            "```",
            "",
        ])
    return "\n".join(lines)


def _iter_source_files(root: Path):
    for current_root, dir_names, file_names in os.walk(root):
        dir_names[:] = [
            name for name in dir_names
            if name not in SKIP_DIR_NAMES and not name.startswith(".pytest_tmp")
        ]
        for file_name in file_names:
            path = Path(current_root) / file_name
            suffix = path.suffix.lower()
            if suffix not in ALLOWED_EXTENSIONS:
                continue
            if any(file_name.lower().endswith(pattern) for pattern in SKIP_FILE_PATTERNS):
                continue
            yield path


def _is_restricted_path(path: Path) -> bool:
    lowered = str(path).lower()
    restricted_terms = (
        "secret",
        "keyvault",
        "private_key",
        "password",
        "token",
        "credential",
        "parameters.backend.local",
    )
    return any(term in lowered for term in restricted_terms)


def _document_record(root: Path, path: Path, chunk: str, chunk_index: int) -> dict:
    relative = path.relative_to(root)
    product = _product_for_root(root)
    title = _title_for_chunk(path, chunk)
    excerpt = _clean_excerpt(chunk)
    tokens = _tokens(f"{title} {relative} {excerpt}")
    return {
        "id": f"{_slug(product)}:{_slug(str(relative))}:{chunk_index}",
        "product": product,
        "path": str(path),
        "relative_path": str(relative),
        "title": title,
        "chunk_index": chunk_index,
        "sensitivity": _classify_sensitivity(product, relative),
        "excerpt": excerpt,
        "tokens": tokens,
    }


def _product_for_root(root: Path) -> str:
    text = str(root).lower()
    if "m-squared" in text or "m_squared" in text:
        return "M2"
    if "diiac" in text:
        return "DIIaC"
    return root.name


def _classify_sensitivity(product: str, relative: Path) -> str:
    parts = [part.lower() for part in relative.parts]
    rel = str(relative).replace("\\", "/").lower()
    if product == "DIIaC" and (rel.startswith("docs/public/") or rel.startswith("docs/product/")):
        return "public_safe"
    if relative.name.lower() in {"readme.md", "agents.md"}:
        return "internal"
    if "governance" in parts or "adr" in parts or "docs" in parts:
        return "internal"
    return "internal"


def _title_for_chunk(path: Path, chunk: str) -> str:
    for line in chunk.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.strip("#").strip() or path.name
    return path.name


def _chunk_text(text: str) -> list[str]:
    text = text.replace("\r\n", "\n")
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    chunks = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= MAX_CHUNK_CHARS:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= MAX_CHUNK_CHARS:
            current = paragraph
        else:
            chunks.extend(_split_long_text(paragraph))
            current = ""
    if current:
        chunks.append(current)
    return chunks


def _split_long_text(text: str) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + MAX_CHUNK_CHARS
        chunks.append(text[start:end])
        start = max(end - CHUNK_OVERLAP_CHARS, end)
    return chunks


def _clean_excerpt(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _tokens(text: str) -> list[str]:
    raw = re.findall(r"[A-Za-z0-9][A-Za-z0-9_\-]{1,}", text.lower())
    stop = {
        "about", "after", "also", "and", "are", "but", "can", "for", "from",
        "has", "into", "not", "that", "the", "this", "with", "without",
    }
    return [token for token in raw if token not in stop]


def _score_document(query_tokens: list[str], document: dict) -> float:
    doc_tokens = document.get("tokens", [])
    if not doc_tokens:
        return 0.0
    counts: dict[str, int] = {}
    for token in doc_tokens:
        counts[token] = counts.get(token, 0) + 1
    score = 0.0
    for token in query_tokens:
        if token in counts:
            score += 1.0 + math.log(1 + counts[token])
        else:
            prefix_hits = sum(1 for doc_token in counts if doc_token.startswith(token) or token.startswith(doc_token))
            if prefix_hits:
                score += min(0.35 * prefix_hits, 1.2)
    if document.get("sensitivity") == "public_safe":
        score *= 1.05
    return score


def _allowed_sensitivities(mode: str) -> set[str]:
    if mode == "public_safe":
        return {"public_safe"}
    return {"public_safe", "internal"}


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value[:80] or "item"
