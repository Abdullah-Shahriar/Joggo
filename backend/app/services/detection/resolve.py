import regex

from app.services.detection.base import (
    Span,
    UNICODE_WORD_BOUNDARY_LEFT,
    UNICODE_WORD_BOUNDARY_RIGHT,
    normalize_bangla_digits,
)
from app.services.detection.dates import detect_dates
from app.services.detection.labels import LABEL_KEYWORDS, detect_labels, is_label_keyword
from app.services.detection.presidio_engine import detect_presidio
from app.services.detection.regex_rules import detect_regex
from app.services.detection.stoplists import BANGLA_STOPWORDS, COMMON_WORDS, MEDICAL_TERMS

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
NAME_TYPE_RANK: dict[str, int] = {
    "PATIENT": 3,
    "DOCTOR": 2,
    "PERSON": 1,
}

TITLE_PREFIX_WORDS: frozenset[str] = frozenset(
    {
        "dr",
        "prof",
        "professor",
        "mr",
        "mrs",
        "ms",
        "md",
        "mst",
        "ডাঃ",
        "ডা",
        "জনাব",
        "মোঃ",
        "মো",
        "মোছাঃ",
        "মোছা",
        "বেগম",
        "শ্রী",
        "শ্রীমতী",
    }
)


def normalize_person_name(raw: str) -> str:
    """Normalize a person name for cross-mention matching (whitespace, case, possessive 's ignored)."""
    cleaned = " ".join(raw.strip().split())
    cleaned = regex.sub(r"['’]s$", "", cleaned, flags=regex.IGNORECASE)
    cleaned = cleaned.strip(".,;:!?\"'’()[]{}।")
    return cleaned.casefold()


def _strip_title_prefix(norm_name: str) -> str:
    parts = norm_name.split()
    while parts and parts[0].rstrip(".") in TITLE_PREFIX_WORDS:
        parts.pop(0)
    return " ".join(parts)


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


def extract_name_components(full_name: str) -> list[str]:
    cleaned_name = regex.sub(r"['’]s\b", "", full_name, flags=regex.IGNORECASE)
    words = regex.findall(r"[\p{L}\p{M}]{3,}", cleaned_name)
    components: list[str] = []
    for w in words:
        low = w.lower()
        if (
            low in TITLE_PREFIX_WORDS
            or w in TITLE_PREFIX_WORDS
            or low in MEDICAL_TERMS
            or low in COMMON_WORDS
            or low in LABEL_KEYWORDS
            or is_label_keyword(w)
            or w in BANGLA_STOPWORDS
        ):
            continue
        if w not in components:
            components.append(w)
    return components


def _is_protected_label_or_medical(text: str, start: int, end: int) -> bool:
    raw = text[start:end].strip()
    if not raw:
        return True
    low = raw.lower().strip(".,;:'’\"")
    if low in MEDICAL_TERMS or low in LABEL_KEYWORDS or is_label_keyword(raw):
        return True
    # Never tokenize a label keyword directly preceding ':' / 'ঃ'
    tail = text[end : end + 3].lstrip(" \t")
    if tail.startswith((":", "ঃ")) and (low in LABEL_KEYWORDS or is_label_keyword(raw)):
        return True
    return False


def _build_person_registry(
    text: str,
    spans: list[Span],
) -> tuple[dict[str, tuple[str, str]], dict[str, tuple[str, str]]]:
    """Build canonical lookup maps: norm_full_name -> (entity_type, canonical_raw) and
    unambiguous norm_component -> (entity_type, canonical_raw).

    Priority: PATIENT > DOCTOR > PERSON, then longer full names over single-word mentions.
    """
    person_spans = [s for s in spans if s.entity_type in NAME_TYPES]
    if not person_spans:
        return {}, {}

    # Sort canonical sources: highest NAME_TYPE_RANK, non-sweep first, then longest value
    def _canon_sort(s: Span) -> tuple[int, int, int, int]:
        val = (s.parent_value or text[s.start : s.end]).strip()
        is_primary = 1 if s.source != "sweep" else 0
        return (
            NAME_TYPE_RANK.get(s.entity_type, 0),
            is_primary,
            len(extract_name_components(val)),
            len(val),
        )

    ordered = sorted(person_spans, key=_canon_sort, reverse=True)
    full_map: dict[str, tuple[str, str]] = {}
    comp_candidates: dict[str, list[tuple[str, str]]] = {}

    # Pass 1: register multi-word canonical names first so single-word mentions (e.g. "Nasrin", "Tareq")
    # resolve to their multi-word canonical person ("Nasrin Akter", "Tareq Hasan") instead of creating
    # separate single-word identities.
    multi_word = [s for s in ordered if len(extract_name_components((s.parent_value or text[s.start : s.end]).strip())) >= 2]
    single_word = [s for s in ordered if len(extract_name_components((s.parent_value or text[s.start : s.end]).strip())) < 2]

    for sp in multi_word:
        raw_val = (sp.parent_value or text[sp.start : sp.end]).strip()
        norm_full = normalize_person_name(raw_val)
        if not norm_full:
            continue
        stripped_full = _strip_title_prefix(norm_full)

        entry = (sp.entity_type, raw_val)
        if norm_full not in full_map:
            full_map[norm_full] = entry
        if stripped_full and stripped_full not in full_map:
            full_map[stripped_full] = entry

        for comp in extract_name_components(raw_val):
            cnorm = comp.casefold()
            existing_list = comp_candidates.setdefault(cnorm, [])
            canon_norm = _strip_title_prefix(normalize_person_name(raw_val))
            if not any(_strip_title_prefix(normalize_person_name(v)) == canon_norm for _t, v in existing_list):
                existing_list.append(entry)

    comp_map: dict[str, tuple[str, str]] = {}
    for cnorm, entries in comp_candidates.items():
        if len(entries) == 1:
            comp_map[cnorm] = entries[0]

    # Pass 2: register single-word people ONLY when they do not already match a multi-word person's component
    for sp in single_word:
        raw_val = (sp.parent_value or text[sp.start : sp.end]).strip()
        norm_full = normalize_person_name(raw_val)
        if not norm_full:
            continue
        stripped_full = _strip_title_prefix(norm_full)
        if stripped_full in comp_map or stripped_full in full_map:
            continue
        entry = (sp.entity_type, raw_val)
        if norm_full not in full_map:
            full_map[norm_full] = entry
        if stripped_full and stripped_full not in full_map:
            full_map[stripped_full] = entry
        for comp in extract_name_components(raw_val):
            cnorm = comp.casefold()
            if cnorm not in comp_map:
                comp_map[cnorm] = entry

    return full_map, comp_map


def _match_known_person(
    raw: str,
    full_map: dict[str, tuple[str, str]],
    comp_map: dict[str, tuple[str, str]],
) -> tuple[str, str] | None:
    norm = normalize_person_name(raw)
    if not norm:
        return None
    if norm in full_map:
        return full_map[norm]
    stripped = _strip_title_prefix(norm)
    if stripped in full_map:
        return full_map[stripped]
    if stripped in comp_map:
        return comp_map[stripped]
    # Check if every non-stopword component of `raw` belongs to the exact same canonical person
    comps = [c.casefold() for c in extract_name_components(raw)]
    if comps:
        matched = [comp_map.get(c) for c in comps]
        if all(m is not None for m in matched):
            unique_targets = {m for m in matched if m is not None}
            if len(unique_targets) == 1:
                return next(iter(unique_targets))
    return None


def detect_metadata_hints(
    text: str,
    metadata_hints: list[str] | None,
    *,
    full_map: dict[str, tuple[str, str]] | None = None,
    comp_map: dict[str, tuple[str, str]] | None = None,
) -> list[Span]:
    if not metadata_hints:
        return []
    spans: list[Span] = []
    fmap = full_map or {}
    cmap = comp_map or {}

    for hint in metadata_hints:
        cleaned = hint.strip()
        if len(cleaned) < 4:
            continue
        matched_person = _match_known_person(cleaned, fmap, cmap)
        entity_type = matched_person[0] if matched_person else "OTHER"
        parent_value = matched_person[1] if matched_person else None

        pattern = regex.compile(
            r"(?i)" + UNICODE_WORD_BOUNDARY_LEFT + regex.escape(cleaned) + UNICODE_WORD_BOUNDARY_RIGHT
        )
        for m in pattern.finditer(text):
            if _is_protected_label_or_medical(text, m.start(), m.end()):
                continue
            spans.append(
                Span(
                    start=m.start(),
                    end=m.end(),
                    entity_type=entity_type,
                    score=0.92,
                    detector="metadata",
                    rule_id="metadata.author_hint",
                    reason="Matched PDF metadata author/creator hint",
                    source="metadata",
                    parent_value=parent_value,
                )
            )
    return spans


def _reconcile_person_entities(text: str, spans: list[Span]) -> list[Span]:
    """Unify person mentions across the document:
    - Re-type NLP LOCATION or OTHER spans matching a known person/component to that person's type & canonical value.
    - Upgrade single-component PERSON spans (e.g. 'Nasrin' or 'Tareq') to their canonical PATIENT/DOCTOR/PERSON value
      so full-name and component mentions always share one placeholder token.
    """
    full_map, comp_map = _build_person_registry(text, spans)
    if not full_map and not comp_map:
        return spans

    updated: list[Span] = []
    for sp in spans:
        if sp.source == "manual":
            updated.append(sp)
            continue

        raw_val = text[sp.start : sp.end].strip()

        # Re-type NLP LOCATION or metadata/auto OTHER spans matching a known person
        if (sp.entity_type == "LOCATION" and sp.detector == "presidio") or sp.entity_type == "OTHER":
            matched = _match_known_person(raw_val, full_map, comp_map)
            if matched is not None:
                canon_type, canon_val = matched
                updated.append(
                    Span(
                        start=sp.start,
                        end=sp.end,
                        entity_type=canon_type,
                        score=max(sp.score, 0.88),
                        detector=sp.detector,
                        rule_id=sp.rule_id,
                        reason=f"Re-typed to {canon_type} matching known person",
                        source=sp.source,
                        parent_value=canon_val,
                    )
                )
                continue

        # Unify NAME_TYPES mentions to their canonical (entity_type, canonical_value)
        if sp.entity_type in NAME_TYPES:
            lookup_str = sp.parent_value or raw_val
            matched = _match_known_person(lookup_str, full_map, comp_map)
            if matched is not None:
                canon_type, canon_val = matched
                if canon_type != sp.entity_type or canon_val != sp.parent_value:
                    updated.append(
                        Span(
                            start=sp.start,
                            end=sp.end,
                            entity_type=canon_type,
                            score=sp.score,
                            detector=sp.detector,
                            rule_id=sp.rule_id,
                            reason=sp.reason,
                            source=sp.source,
                            parent_value=canon_val,
                        )
                    )
                    continue

        updated.append(sp)

    return updated


def _is_covered_by_protected_priority(start: int, end: int, resolved: list[Span], candidate_priority: int) -> bool:
    """Return True if an existing span overlapping [start, end) has priority >= candidate_priority."""
    for s in resolved:
        if start < s.end and end > s.start:
            if _priority(s) >= candidate_priority:
                return True
    return False


def run_literal_sweep(text: str, resolved: list[Span]) -> list[Span]:
    """Step 6 sweep (architecture.md §12): sweep name components and exact literal values.

    Overrides overlapping lower-priority spans (LOCATION, OTHER) for person names, while never
    replacing protected medical terms or clinical label keywords.
    """
    extra: list[Span] = []
    norm_text = normalize_bangla_digits(text)

    for span in resolved:
        raw_val = text[span.start : span.end].strip()
        if not raw_val or len(raw_val) < 3:
            continue
        if span.entity_type in {"DATE", "DOB", "AGE90"}:
            continue
        if _is_protected_label_or_medical(text, span.start, span.end):
            continue

        canonical_parent = span.parent_value or raw_val
        cand_priority = TYPE_PRIORITY.get(span.entity_type, 20)

        # Exact literal sweep for all non-date entities (Unicode-aware boundaries for Bangla & English)
        if any(ch.isdigit() for ch in raw_val):
            lit_pat = regex.compile(regex.escape(normalize_bangla_digits(raw_val)), regex.IGNORECASE)
            search_target = norm_text
        else:
            lit_pat = regex.compile(
                r"(?i)" + UNICODE_WORD_BOUNDARY_LEFT + regex.escape(raw_val) + UNICODE_WORD_BOUNDARY_RIGHT
            )
            search_target = text

        for m in lit_pat.finditer(search_target):
            if _is_protected_label_or_medical(text, m.start(), m.end()):
                continue
            if not _is_covered_by_protected_priority(m.start(), m.end(), resolved, cand_priority):
                extra.append(
                    Span(
                        start=m.start(),
                        end=m.end(),
                        entity_type=span.entity_type,
                        score=max(0.78, span.score - 0.05),
                        detector="sweep",
                        rule_id="sweep.exact_literal",
                        reason=f"Repeated occurrence of detected {span.entity_type}",
                        source="sweep",
                        parent_value=canonical_parent,
                    )
                )

        # Name-component sweep for PATIENT / DOCTOR / PERSON (Unicode-aware for Bangla & English)
        if span.entity_type in NAME_TYPES:
            for comp in extract_name_components(canonical_parent):
                comp_pat = regex.compile(
                    r"(?i)" + UNICODE_WORD_BOUNDARY_LEFT + regex.escape(comp) + UNICODE_WORD_BOUNDARY_RIGHT
                )
                for m in comp_pat.finditer(text):
                    if _is_protected_label_or_medical(text, m.start(), m.end()):
                        continue
                    # Override lower-priority spans (LOCATION=30, OTHER=20) with the person's token (50)
                    if not _is_covered_by_protected_priority(m.start(), m.end(), resolved, cand_priority):
                        extra.append(
                            Span(
                                start=m.start(),
                                end=m.end(),
                                entity_type=span.entity_type,
                                score=0.82,
                                detector="sweep",
                                rule_id="sweep.name_component",
                                reason=f"Name component matched from detected {span.entity_type}",
                                source="sweep",
                                parent_value=canonical_parent,
                            )
                        )

    merged = resolve_overlaps(resolved + extra)
    return _reconcile_person_entities(text, merged)


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
    if manual_spans:
        candidates.extend(manual_spans)

    # Filter out any non-manual span that directly targets a clinical label keyword
    candidates = [
        s
        for s in candidates
        if s.source == "manual"
        or s.entity_type in {"DATE", "DOB", "AGE90", "EMAIL", "URL", "IP", "PHONE", "MRN", "ID"}
        or not _is_protected_label_or_medical(text, s.start, s.end)
    ]

    # Build person registry from detected people so metadata hints reuse their entity type & token
    full_map, comp_map = _build_person_registry(text, candidates)
    candidates.extend(
        detect_metadata_hints(text, metadata_hints, full_map=full_map, comp_map=comp_map)
    )

    resolved = resolve_overlaps(candidates)
    resolved = _reconcile_person_entities(text, resolved)
    if include_sweep:
        resolved = run_literal_sweep(text, resolved)
    return resolved
