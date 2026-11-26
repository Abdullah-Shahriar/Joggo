from collections.abc import Iterator
from datetime import date, datetime, timezone
import re

from dateutil import parser as dateutil_parser
import regex

from app.config import get_settings
from app.services.detection.base import (
    Span,
    UNICODE_WORD_BOUNDARY_LEFT,
    UNICODE_WORD_BOUNDARY_RIGHT,
    has_adjacent_medical_unit,
    normalize_bangla_digits,
)

MONTH_NAMES = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)

# Date candidate patterns (architecture.md §12). Year-only mentions (e.g. "in 2019") are NOT matched.
# Numeric patterns require one consistent separator (., /, or -) via backreference \1 and avoid
# matching 4-part IPv4 addresses or decimal prefixes/suffixes.
DATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("date.iso", re.compile(r"(?<!\d)(?<!\.)\d{4}([./-])\d{1,2}\1\d{1,2}(?!\d)(?!\.\d)")),
    ("date.dmy_numeric", re.compile(r"(?<!\d)(?<!\.)\d{1,2}([./-])\d{1,2}\1\d{2,4}(?!\d)(?!\.\d)")),
    ("date.day_month_year", re.compile(rf"\b\d{{1,2}}\s+(?:{MONTH_NAMES})\.?,?\s+\d{{2,4}}\b", re.IGNORECASE)),
    ("date.month_day_year", re.compile(rf"\b(?:{MONTH_NAMES})\.?\s+\d{{1,2}},?\s+\d{{2,4}}\b", re.IGNORECASE)),
    ("date.day_month", re.compile(rf"\b\d{{1,2}}\s+(?:{MONTH_NAMES})\b(?!\s*,?\s*\d{{2,4}})", re.IGNORECASE)),
)

DOB_CONTEXT_RE = regex.compile(
    r"(?i)(?:"
    + UNICODE_WORD_BOUNDARY_LEFT
    + r"(?:DOB|D\.O\.B\.?|Date\s+of\s+Birth|Born|Birth\s+Date)"
    + UNICODE_WORD_BOUNDARY_RIGHT
    + r"|জন্ম\s*তারিখ)"
)

# Context words required within 25 chars for dotted 2-digit-year dates (e.g. "DOB: 02.07.79", "on 12.10.26")
DOTTED_SHORT_YEAR_CONTEXT_RE = regex.compile(
    r"(?i)(?:"
    + UNICODE_WORD_BOUNDARY_LEFT
    + r"(?:DOB|D\.O\.B\.?|Date\s+of|Born|Birth\s+Date|admitted|admission|DOA|discharged|discharge|on)"
    + UNICODE_WORD_BOUNDARY_RIGHT
    + r"|জন্ম\s*তারিখ|ভর্তির\s*তারিখ)"
)

VERSION_PREFIX_RE = re.compile(r"(?i)(?:\b(?:ver(?:sion)?|rel(?:ease)?|build)\.?[\s:_-]*|\bv\.?)$")

# Ages >= 90 (architecture.md §12), English and Bangla
AGE90_RE = regex.compile(
    UNICODE_WORD_BOUNDARY_LEFT
    + r"(9\d|1[0-4]\d)\s*(?:y(?:ea)?rs?|y/o|yo|years?|বছর)"
    + UNICODE_WORD_BOUNDARY_RIGHT,
    regex.IGNORECASE,
)


def _apply_two_digit_year_pivot(dt: date, raw: str) -> date:
    """Two-digit year pivot: <= current yy -> 20yy else 19yy (architecture.md §12)."""
    m = re.search(r"([./-]|\s)(\d{2})$", raw.strip())
    if not m:
        return dt
    yy = int(m.group(2))
    current_yy = datetime.now(timezone.utc).year % 100
    target_year = (2000 + yy) if yy <= current_yy else (1900 + yy)
    try:
        return dt.replace(year=target_year)
    except ValueError:
        return dt


def _parse_date_candidate(raw: str, *, dayfirst: bool, has_year: bool) -> date | None:
    try:
        default_dt = datetime(datetime.now(timezone.utc).year, 1, 1)
        parsed = dateutil_parser.parse(raw, dayfirst=dayfirst, default=default_dt, fuzzy=False).date()
    except (ValueError, OverflowError):
        return None
    if has_year:
        parsed = _apply_two_digit_year_pivot(parsed, raw)
    return parsed


def iter_valid_date_matches(
    text: str,
    *,
    date_order: str | None = None,
) -> Iterator[tuple[str, re.Match[str], date | None, bool]]:
    """Yield (rule_id, match, parsed_date, is_dob) for validated date candidates on `text`.

    Shared by `detect_dates` and `safety.py` so dotted dates, medical-unit guards, version guards,
    and 2-digit dotted-year context rules behave identically in both stages.
    """
    order = (date_order or get_settings().DATE_ORDER).upper()
    dayfirst = order == "DMY"
    # 1-to-1 digit translation preserves exact character offsets on `text`.
    norm = normalize_bangla_digits(text)

    for rule_id, pattern in DATE_PATTERNS:
        has_year = rule_id != "date.day_month"
        is_numeric = rule_id in {"date.iso", "date.dmy_numeric"}
        for m in pattern.finditer(norm):
            raw = m.group(0)
            # Never match values followed within 3 chars by a clinical/medical unit
            if has_adjacent_medical_unit(text, m.end()):
                continue

            sep = m.group(1) if is_numeric else ""
            prefix_window = text[max(0, m.start() - 25) : m.start()]

            if sep == ".":
                # Guard against software version numbers (e.g., "v1.2.26", "version 2.4.1")
                version_window = text[max(0, m.start() - 12) : m.start()]
                if VERSION_PREFIX_RE.search(version_window):
                    continue

                # For 2-digit years with dots (e.g. "02.07.79"), require date context within 25 chars
                parts = raw.split(".")
                if rule_id == "date.dmy_numeric" and len(parts) == 3 and len(parts[2]) == 2:
                    if not DOTTED_SHORT_YEAR_CONTEXT_RE.search(prefix_window):
                        continue

            is_dob = bool(DOB_CONTEXT_RE.search(prefix_window))

            # For ISO dates (YYYY-MM-DD / YYYY.MM.DD), dayfirst must be False
            parsed = _parse_date_candidate(
                raw,
                dayfirst=(False if rule_id == "date.iso" else dayfirst),
                has_year=has_year,
            )

            if sep == ".":
                # Dotted candidates must parse as a real calendar date within plausible clinical years
                if parsed is None or parsed.year < 1900 or parsed.year > 2100:
                    continue

            yield rule_id, m, parsed, is_dob


def detect_dates(text: str, *, date_order: str | None = None) -> list[Span]:
    spans: list[Span] = []
    norm = normalize_bangla_digits(text)

    for rule_id, m, parsed, is_dob in iter_valid_date_matches(text, date_order=date_order):
        entity_type = "DOB" if is_dob else "DATE"
        reason = (
            "Date of birth converted to age"
            if is_dob
            else ("Unparseable date-shaped value" if parsed is None else "Calendar date converted to relative day")
        )
        spans.append(
            Span(
                start=m.start(),
                end=m.end(),
                entity_type=entity_type,
                score=0.95 if is_dob else 0.90,
                detector="dates",
                rule_id="date.dob" if is_dob else rule_id,
                reason=reason,
                unparsed=(parsed is None),
                parsed_date=parsed,
            )
        )

    for m in AGE90_RE.finditer(norm):
        spans.append(
            Span(
                start=m.start(),
                end=m.end(),
                entity_type="AGE90",
                score=0.95,
                detector="dates",
                rule_id="date.age90",
                reason="Age >= 90 generalized to 90+ years (HIPAA Safe Harbor)",
            )
        )

    return spans
