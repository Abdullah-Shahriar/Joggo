from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import re
from typing import Any

import regex

from app.services.detection.base import Span, normalize_bangla_digits
from app.services.detection.resolve import NAME_TYPES, extract_name_components

ADMISSION_ANCHOR_RE = regex.compile(
    r"(?i)(?:\b(?:Date\s+of\s+Admission|Admitted|Admission|DOA)\b|ভর্তির\s*তারিখ)"
)
SECONDARY_ANCHOR_RE = re.compile(
    r"(?i)\bDate\s+of\s+(?:Report|Collection|Sample|Service|Visit)\b"
)


@dataclass(frozen=True)
class EntityRowData:
    token: str
    entity_type: str
    source: str
    detector: str
    rule_id: str
    reason: str
    score: Decimal
    occurrences: int


@dataclass(frozen=True)
class TokenizationResult:
    sanitized_text: str
    mapping: dict[str, str]
    vault_entities: list[dict[str, Any]]
    entity_rows: list[EntityRowData]
    entity_summary: dict[str, int]
    anchor_date: str | None
    name_components: list[str]


def _index_to_letters(idx: int) -> str:
    """1 -> A, 2 -> B, ..., 26 -> Z, 27 -> AA."""
    chars: list[str] = []
    n = idx
    while n > 0:
        n, rem = divmod(n - 1, 26)
        chars.append(chr(ord("A") + rem))
    return "".join(reversed(chars))


def normalize_entity_value(entity_type: str, raw: str) -> str:
    cleaned = normalize_bangla_digits(" ".join(raw.strip().split()))
    if entity_type == "PHONE":
        digits = re.sub(r"\D", "", cleaned)
        if digits.startswith("8801") and len(digits) == 13:
            digits = digits[2:]
        return digits or cleaned.casefold()
    if entity_type in {"ID", "MRN"}:
        alnum = re.sub(r"[^A-Za-z0-9]", "", cleaned).casefold()
        return alnum or cleaned.casefold()
    stripped = cleaned.strip(".,;:!?\"'()[]{}।")
    return stripped.casefold()


def _select_anchor_date(text: str, spans: list[Span]) -> date | None:
    date_spans = [s for s in spans if s.entity_type == "DATE" and s.parsed_date is not None]
    if not date_spans:
        return None

    for s in date_spans:
        prefix = text[max(0, s.start - 35) : s.start]
        if ADMISSION_ANCHOR_RE.search(prefix):
            return s.parsed_date

    for s in date_spans:
        prefix = text[max(0, s.start - 35) : s.start]
        if SECONDARY_ANCHOR_RE.search(prefix):
            return s.parsed_date

    return min(s.parsed_date for s in date_spans if s.parsed_date is not None)


def _full_years_between(dob: date, ref: date) -> int:
    years = ref.year - dob.year - ((ref.month, ref.day) < (dob.month, dob.day))
    return max(0, years)


def tokenize_text(text: str, resolved_spans: list[Span]) -> TokenizationResult:
    """Assign deterministic context-preserving tokens and render sanitized text (architecture.md §13)."""
    ordered = sorted(resolved_spans, key=lambda s: (s.start, s.end))
    anchor_date = _select_anchor_date(text, ordered)

    counters: dict[str, int] = {}
    value_to_token: dict[tuple[str, str], str] = {}
    mapping: dict[str, str] = {}
    name_components_set: dict[str, None] = {}

    # Track entity metadata per unique token for document_entities rows
    token_meta: dict[str, dict[str, Any]] = {}
    vault_entities: list[dict[str, Any]] = []
    replacements: list[tuple[int, int, str]] = []

    dob_count = 0
    age90_count = 0

    for span in ordered:
        raw_val = text[span.start : span.end]
        etype = span.entity_type

        if etype == "DOB":
            if span.parsed_date is None or span.unparsed:
                replacement = "[DAY_?]"
                db_token = "[DAY_?]"
            else:
                ref = anchor_date or datetime.now(timezone.utc).date()
                age_years = _full_years_between(span.parsed_date, ref)
                replacement = "Age 90+" if age_years > 89 else f"Age {age_years}"
                dob_count += 1
                db_token = "AGE_CALC" if dob_count == 1 else f"AGE_CALC_{dob_count}"

            replacements.append((span.start, span.end, replacement))
            vault_entities.append(
                {
                    "start": span.start,
                    "end": span.end,
                    "type": etype,
                    "token": replacement,
                    "source": span.source,
                    "rule": span.rule_id,
                }
            )
            if db_token not in token_meta:
                token_meta[db_token] = {
                    "entity_type": etype,
                    "source": span.source,
                    "detector": span.detector,
                    "rule_id": span.rule_id,
                    "reason": span.reason,
                    "score": Decimal(f"{span.score:.3f}"),
                    "occurrences": 1,
                }
            else:
                token_meta[db_token]["occurrences"] += 1
            continue

        if etype == "AGE90":
            replacement = "90+ years"
            age90_count += 1
            db_token = "AGE_90_PLUS" if age90_count == 1 else f"AGE_90_PLUS_{age90_count}"
            replacements.append((span.start, span.end, replacement))
            vault_entities.append(
                {
                    "start": span.start,
                    "end": span.end,
                    "type": etype,
                    "token": replacement,
                    "source": span.source,
                    "rule": span.rule_id,
                }
            )
            if db_token not in token_meta:
                token_meta[db_token] = {
                    "entity_type": etype,
                    "source": span.source,
                    "detector": span.detector,
                    "rule_id": span.rule_id,
                    "reason": span.reason,
                    "score": Decimal(f"{span.score:.3f}"),
                    "occurrences": 1,
                }
            else:
                token_meta[db_token]["occurrences"] += 1
            continue

        if etype == "DATE":
            if span.parsed_date is None or span.unparsed or anchor_date is None:
                token = "[DAY_?]"
            else:
                delta_days = (span.parsed_date - anchor_date).days
                token = f"[DAY_{delta_days}]"
                if token not in mapping:
                    mapping[token] = raw_val

            replacements.append((span.start, span.end, token))
            vault_entities.append(
                {
                    "start": span.start,
                    "end": span.end,
                    "type": etype,
                    "token": token,
                    "source": span.source,
                    "rule": span.rule_id,
                }
            )
            if token not in token_meta:
                token_meta[token] = {
                    "entity_type": etype,
                    "source": span.source,
                    "detector": span.detector,
                    "rule_id": span.rule_id,
                    "reason": span.reason,
                    "score": Decimal(f"{span.score:.3f}"),
                    "occurrences": 1,
                }
            else:
                token_meta[token]["occurrences"] += 1
            continue

        # Standard named/structured entity types
        key_source_val = span.parent_value if (span.source == "sweep" and span.parent_value) else raw_val
        norm = normalize_entity_value(etype, key_source_val)
        lookup_key = (etype, norm)

        if lookup_key not in value_to_token:
            counters[etype] = counters.get(etype, 0) + 1
            idx = counters[etype]
            if etype == "PATIENT":
                token = f"[PATIENT_{_index_to_letters(idx)}]"
            else:
                token = f"[{etype}_{idx}]"
            value_to_token[lookup_key] = token
            mapping[token] = key_source_val.strip()
        else:
            token = value_to_token[lookup_key]

        if etype in NAME_TYPES:
            for comp in extract_name_components(raw_val):
                name_components_set[comp] = None

        replacements.append((span.start, span.end, token))
        vault_entities.append(
            {
                "start": span.start,
                "end": span.end,
                "type": etype,
                "token": token,
                "source": span.source,
                "rule": span.rule_id,
            }
        )
        if token not in token_meta:
            token_meta[token] = {
                "entity_type": etype,
                "source": span.source,
                "detector": span.detector,
                "rule_id": span.rule_id,
                "reason": span.reason,
                "score": Decimal(f"{span.score:.3f}"),
                "occurrences": 1,
            }
        else:
            token_meta[token]["occurrences"] += 1

    # Single-pass right-to-left replacement by offsets
    out = text
    for start, end, repl in sorted(replacements, key=lambda r: r[0], reverse=True):
        out = out[:start] + repl + out[end:]

    entity_rows = [
        EntityRowData(
            token=tok,
            entity_type=meta["entity_type"],
            source=meta["source"],
            detector=meta["detector"],
            rule_id=meta["rule_id"],
            reason=meta["reason"],
            score=meta["score"],
            occurrences=meta["occurrences"],
        )
        for tok, meta in token_meta.items()
    ]

    entity_summary: dict[str, int] = {}
    for row in entity_rows:
        entity_summary[row.entity_type] = entity_summary.get(row.entity_type, 0) + row.occurrences

    return TokenizationResult(
        sanitized_text=out,
        mapping=mapping,
        vault_entities=vault_entities,
        entity_rows=entity_rows,
        entity_summary=entity_summary,
        anchor_date=anchor_date.isoformat() if anchor_date else None,
        name_components=list(name_components_set.keys()),
    )
