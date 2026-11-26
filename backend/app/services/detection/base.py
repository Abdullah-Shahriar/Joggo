from dataclasses import dataclass
from datetime import date
import re

ENTITY_TYPES: frozenset[str] = frozenset(
    {
        "PATIENT",
        "DOCTOR",
        "PERSON",
        "PHONE",
        "EMAIL",
        "ID",
        "MRN",
        "LOCATION",
        "FACILITY",
        "URL",
        "IP",
        "DOB",
        "DATE",
        "AGE90",
        "OTHER",
    }
)

MANUAL_MARK_TYPES: frozenset[str] = frozenset(
    {
        "PATIENT",
        "DOCTOR",
        "PERSON",
        "PHONE",
        "EMAIL",
        "ID",
        "MRN",
        "LOCATION",
        "FACILITY",
        "OTHER",
    }
)

MEDICAL_UNIT_AFTER_RE = re.compile(
    r"^\s{0,3}(?:mg/dL|g/dL|U/L|mmHg|mmol/L|mmol|mg|ml|mL|bpm|cm|kg|IU|µg|ug|ng|%)(?![A-Za-z])",
    re.IGNORECASE,
)

TOKEN_PATTERN_RE = re.compile(
    r"\[(?:PATIENT|DOCTOR|PERSON|PHONE|EMAIL|ID|MRN|LOCATION|FACILITY|URL|IP|OTHER|DAY)_[A-Z0-9?-]+\]"
)

BANGLA_DIGIT_TRANS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

# Unicode-aware word boundaries for regex module (handles Bangla vowel signs / combining marks \p{M}).
UNICODE_WORD_BOUNDARY_LEFT = r"(?<![\p{L}\p{N}\p{M}])"
UNICODE_WORD_BOUNDARY_RIGHT = r"(?![\p{L}\p{N}\p{M}])"


def normalize_bangla_digits(text: str) -> str:
    """Map Bangla digits ০-৯ 1-to-1 to ASCII 0-9 while preserving exact character offsets."""
    return text.translate(BANGLA_DIGIT_TRANS)


def has_adjacent_medical_unit(text: str, end: int) -> bool:
    tail = text[end : end + 12]
    return bool(MEDICAL_UNIT_AFTER_RE.match(tail))


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    entity_type: str
    score: float
    detector: str
    rule_id: str
    reason: str
    source: str = "auto"
    unparsed: bool = False
    parsed_date: date | None = None
    parent_value: str | None = None
