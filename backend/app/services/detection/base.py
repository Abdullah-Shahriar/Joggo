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
