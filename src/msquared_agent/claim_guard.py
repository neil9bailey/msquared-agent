import re
from typing import List, Tuple


FORBIDDEN_CLAIMS = [
    (
        "diia_certifies_compliance",
        r"(?i)\bDIIaC\b.*\b(certif(?:y|ies|ied|ication)|compliance certified|guarantees compliance|fully compliant)\b",
    ),
    (
        "diia_autonomously_approves",
        r"(?i)(?:\bDIIaC\b|M²|M2).*\b(autonomously approves|auto-approves|approves decisions without human)\b",
    ),
    (
        "m2_proves_truth",
        r"(?i)(?:M²|M2).*\b(proves truth|proves.*truth|certifies truth|knows model intent)\b",
    ),
    (
        "m2_reads_model_internals",
        r"(?i)(?:M²|M2).*\b(reads all upstream model internals|reads.*activation|internal.*state)\b",
    ),
    (
        "m2_or_diiac_overrides",
        r"(?i)(?:M²|M2|\bDIIaC\b).*\boverrides\b",
    ),
    (
        "replaces_systems_of_record",
        r"(?i)(?:M²|M2|\bDIIaC\b).*\breplaces systems of record\b",
    ),
    (
        "unconfirmed_iapp_inclusion",
        r"(?i)\b(IAPP)\b.*\b(inclusion|included|added to report)\b",
    ),
]


def check_claims(text: str) -> Tuple[str, List[str]]:
    matches = [claim_id for claim_id, pattern in FORBIDDEN_CLAIMS if re.search(pattern, text or "")]
    return ("block" if matches else "low", matches)
