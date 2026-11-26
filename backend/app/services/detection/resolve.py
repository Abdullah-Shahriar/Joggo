import re

from app.services.detection.base import Span
from app.services.detection.dates import detect_dates
from app.services.detection.labels import detect_labels
from app.services.detection.presidio_engine import detect_presidio
from app.services.detection.regex_rules import detect_regex
from app.services.detection.stoplists import COMMON_WORDS, MEDICAL_TERMS

TYPE_PRIORITY: dict[str, int] = {
    "MRN": 90,
    "ID": 90,
    "PHONE": 90,
    "EMAIL": 90,
    "URL": 90,
    "IP": 90,
    "DOB": 70,
    "DATE": 70,
    "AGE90": 70,
    "PATIENT": 50,
    "DOCTOR": 50,
    "PERSON": 50,
    "LOCATION": 30,
    "FACILITY": 30,
    "OTHER": 20,
}

NAME_TYPES: frozenset[str] = frozenset({"PATIENT", "DOCTOR", "PERSON"})
TITLE_PREFIX_WORDS: frozenset[str] = frozenset({"dr", "prof", "professor", "mr", "mrs", "ms", "md", "mst"})


def _priority(span: Span) -> int:
    # Manual marks from the clinician always win over auto detections
    if span.source == "manual":
        return 100
    return TYPE_PRIORITY.get(span.entity_type, 20)


def _rank_key(span: Span) -> tuple[int, float, int]:
    return (_priority(span), span.score, span.end - span.start)


def resolve_overlaps(spans: list[Span]) -> list[Span]:
    """Deterministic overlap resolution per architecture.md §12."""
    valid = [s for s in spans if s.end > s.start]
    if not valid:
        return []

    ordered = sorted(valid, key=lambda s: (s.start, -(s.end - s.start), -_priority(s), -s.score, s.rule_id))
    kept: list[Span] = []

    for candidate in ordered:
        overlapping_indices = [
            idx for idx, existing in enumerate(kept) if candidate.start < existing.end and candidate.end > existing.start
        ]
        if not overlapping_indices:
            kept.append(candidate)
            continue

        # Candidate wins only if it strictly beats every overlapping kept span
        cand_rank = _rank_key(candidate)
        if all(cand_rank > _rank_key(kept[idx]) for idx in overlapping_indices):
            for idx in reversed(overlapping_indices):
                kept.pop(idx)
            kept.append(candidate)

    return sorted(kept, key=lambda s: (s.start, s.end))


def detect_metadata_hints(text: str, metadata_hints: list[str] | None) -> list[Span]:
    if not metadata_hints:
        return []
    spans: list[Span] = []
    for hint in metadata_hints:
        cleaned = hint.strip()
        if len(cleaned) < 4:
            continue
        pattern = re.compile(r"(?i)(?<!\w)" + re.escape(cleaned) + r"(?!\w)")
        for m in pattern.finditer(text):
            spans.append(
                Span(
                    start=m.start(),
                    end=m.end(),
                    entity_type="OTHER",
                    score=0.92,
                    detector="metadata",
                    rule_id="metadata.author_hint",
                    reason="Matched PDF metadata author/creator hint",
                    source="metadata",
                )
            )
    return spans


def extract_name_components(full_name: str) -> list[str]:
    words = re.findall(r"[A-Za-z]{3,}", full_name)
    components: list[str] = []
    for w in words:
        low = w.lower()
        if low in TITLE_PREFIX_WORDS or low in MEDICAL_TERMS or low in COMMON_WORDS:
            continue
        if w not in components:
            components.append(w)
    return components


def _is_covered(start: int, end: int, resolved: list[Span]) -> bool:
    return any(start < s.end and end > s.start for s in resolved)


def run_literal_sweep(text: str, resolved: list[Span]) -> list[Span]:
    """Step 6 sweep (architecture.md §12): sweep name components and exact literal values."""
    extra: list[Span] = []

    for span in resolved:
        raw_val = text[span.start : span.end].strip()
        if not raw_val or len(raw_val) < 3:
            continue
        if span.entity_type in {"DATE", "DOB", "AGE90"}:
            continue

        # Exact literal sweep for all non-date entities
        if any(ch.isdigit() for ch in raw_val):
            lit_pat = re.compile(re.escape(raw_val), re.IGNORECASE)
        else:
            lit_pat = re.compile(r"(?i)(?<!\w)" + re.escape(raw_val) + r"(?!\w)")

        for m in lit_pat.finditer(text):
            if not _is_covered(m.start(), m.end(), resolved):
                extra.append(
                    Span(
                        start=m.start(),
                        end=m.end(),
                        entity_type=span.entity_type,
                        score=max(0.75, span.score - 0.05),
                        detector="sweep",
                        rule_id="sweep.exact_literal",
                        reason=f"Repeated occurrence of detected {span.entity_type}",
                        source="sweep",
                        parent_value=raw_val,
                    )
                )

        # Name-component sweep for PATIENT / DOCTOR / PERSON
        if span.entity_type in NAME_TYPES:
            for comp in extract_name_components(raw_val):
                comp_pat = re.compile(r"(?i)\b" + re.escape(comp) + r"\b")
                for m in comp_pat.finditer(text):
                    if not _is_covered(m.start(), m.end(), resolved):
                        extra.append(
                            Span(
                                start=m.start(),
                                end=m.end(),
                                entity_type=span.entity_type,
                                score=0.80,
                                detector="sweep",
                                rule_id="sweep.name_component",
                                reason=f"Name component matched from detected {span.entity_type}",
                                source="sweep",
                                parent_value=raw_val,
                            )
                        )

    return resolve_overlaps(resolved + extra)


def run_detection(
    text: str,
    *,
    metadata_hints: list[str] | None = None,
    date_order: str | None = None,
    manual_spans: list[Span] | None = None,
    use_presidio: bool = True,
    include_sweep: bool = True,
) -> list[Span]:
    candidates: list[Span] = []
    candidates.extend(detect_regex(text))
    candidates.extend(detect_labels(text))
    candidates.extend(detect_dates(text, date_order=date_order))
    if use_presidio:
        candidates.extend(detect_presidio(text))
    candidates.extend(detect_metadata_hints(text, metadata_hints))
    if manual_spans:
        candidates.extend(manual_spans)

    resolved = resolve_overlaps(candidates)
    if include_sweep:
        resolved = run_literal_sweep(text, resolved)
    return resolved
