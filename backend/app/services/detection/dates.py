from datetime import date, datetime, timezone
import re

from dateutil import parser as dateutil_parser

from app.config import get_settings
from app.services.detection.base import Span

MONTH_NAMES = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)

# Date candidate patterns (architecture.md §12). Year-only mentions (e.g. "in 2019") are NOT matched.
DATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("date.iso", re.compile(r"(?<!\d)\d{4}[-/]\d{1,2}[-/]\d{1,2}(?!\d)")),
    ("date.dmy_numeric", re.compile(r"(?<!\d)\d{1,2}[/-]\d{1,2}[/-]\d{2,4}(?!\d)")),
    ("date.day_month_year", re.compile(rf"\b\d{{1,2}}\s+(?:{MONTH_NAMES})\.?,?\s+\d{{2,4}}\b", re.IGNORECASE)),
    ("date.month_day_year", re.compile(rf"\b(?:{MONTH_NAMES})\.?\s+\d{{1,2}},?\s+\d{{2,4}}\b", re.IGNORECASE)),
    ("date.day_month", re.compile(rf"\b\d{{1,2}}\s+(?:{MONTH_NAMES})\b(?!\s*,?\s*\d{{2,4}})", re.IGNORECASE)),
)

DOB_CONTEXT_RE = re.compile(r"(?i)\b(?:DOB|D\.O\.B\.?|Date\s+of\s+Birth|Born|Birth\s+Date)\b")

# Ages >= 90 (architecture.md §12)
AGE90_RE = re.compile(r"\b(9\d|1[0-4]\d)\s*(?:y(?:ea)?rs?|y/o|yo|years?)\b", re.IGNORECASE)


def _apply_two_digit_year_pivot(dt: date, raw: str) -> date:
    """Two-digit year pivot: <= current yy -> 20yy else 19yy (architecture.md §12)."""
    m = re.search(r"([/-]|\s)(\d{2})$", raw.strip())
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


def detect_dates(text: str, *, date_order: str | None = None) -> list[Span]:
    order = (date_order or get_settings().DATE_ORDER).upper()
    dayfirst = order == "DMY"
    spans: list[Span] = []

    for rule_id, pattern in DATE_PATTERNS:
        has_year = rule_id != "date.day_month"
        for m in pattern.finditer(text):
            raw = m.group(0)
            # Check if this date appears within 25 chars after a DOB label
            prefix_window = text[max(0, m.start() - 25) : m.start()]
            is_dob = bool(DOB_CONTEXT_RE.search(prefix_window))

            # For ISO dates (YYYY-MM-DD), dayfirst must be False
            parsed = _parse_date_candidate(
                raw,
                dayfirst=(False if rule_id == "date.iso" else dayfirst),
                has_year=has_year,
            )

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

    for m in AGE90_RE.finditer(text):
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
