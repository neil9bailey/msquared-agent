import re
import unicodedata


NON_LATIN_OMITTED = "[non-Latin text omitted]"

_TRANSLATION = str.maketrans({
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2122": "(TM)",
})

_STRONG_PRODUCT_TERMS = (
    "diiac",
    "msquared",
    "m squared",
    "m-squared",
    "m2",
)
_SUPPORTING_PRODUCT_TERMS = (
    "ai governance",
    "decision intelligence",
    "governed decision",
    "human-machine",
    "reasoning signals",
)


def normalize_text(value: str | None) -> str:
    text = "" if value is None else str(value)
    text = text.translate(_TRANSLATION)
    text = unicodedata.normalize("NFKC", text)
    output = []
    for character in text:
        category = unicodedata.category(character)
        if character in {"\n", "\t"}:
            output.append(character)
        elif category.startswith("C"):
            output.append(" ")
        else:
            output.append(character)
    return re.sub(r"[ \t]+", " ", "".join(output)).strip()


def display_excerpt(value: str | None, limit: int = 180) -> str:
    cleaned = _omit_non_latin_runs(normalize_text(value))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return _truncate(cleaned, limit)


def product_excerpt(value: str | None, limit: int = 180) -> str:
    normalized = normalize_text(value)
    chunks = _chunks(normalized)
    if not chunks:
        return ""

    best_index = -1
    best_score = 0
    for index, chunk in enumerate(chunks):
        score = _product_score(chunk)
        if score > best_score:
            best_index = index
            best_score = score

    if best_index >= 0:
        selected = " ".join(chunks[best_index: best_index + 3])
    else:
        selected = normalized
    return display_excerpt(selected, limit=limit)


def contains_non_latin_text(value: str | None) -> bool:
    return any(_is_non_latin_letter(character) for character in normalize_text(value))


def _product_score(value: str) -> int:
    lowered = value.lower()
    score = 0
    for term in _STRONG_PRODUCT_TERMS:
        if term in lowered:
            score += 5
    for term in _SUPPORTING_PRODUCT_TERMS:
        if term in lowered:
            score += 2
    return score


def _chunks(value: str) -> list[str]:
    candidates = []
    for line in value.splitlines():
        line = line.strip()
        if not line:
            continue
        candidates.extend(part.strip() for part in re.split(r"(?<=[.!?])\s+", line) if part.strip())
    if not candidates and value.strip():
        candidates.append(value.strip())
    return candidates


def _omit_non_latin_runs(value: str) -> str:
    output = []
    in_non_latin_run = False
    placeholder_added = False
    for character in value:
        if _is_non_latin_letter(character) or _is_non_latin_mark(character):
            if not in_non_latin_run and not placeholder_added:
                output.append(f" {NON_LATIN_OMITTED} ")
                placeholder_added = True
            in_non_latin_run = True
            continue
        in_non_latin_run = False
        if not character.isspace():
            placeholder_added = False
        output.append(character)
    return re.sub(r"\s+", " ", "".join(output)).strip()


def _is_non_latin_letter(character: str) -> bool:
    if not unicodedata.category(character).startswith("L"):
        return False
    name = unicodedata.name(character, "")
    return "LATIN" not in name


def _is_non_latin_mark(character: str) -> bool:
    if not unicodedata.category(character).startswith("M"):
        return False
    name = unicodedata.name(character, "")
    return any(script in name for script in ("ARABIC", "THAI", "HEBREW", "DEVANAGARI"))


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    truncated = value[: max(limit - 3, 0)].rstrip()
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0].rstrip()
    return f"{truncated}..."
