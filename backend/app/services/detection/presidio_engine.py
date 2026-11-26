import logging
import re
import threading

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider
import regex

from app.config import get_settings
from app.services.detection.base import Span, has_adjacent_medical_unit
from app.services.detection.labels import LABEL_KEYWORDS, is_label_keyword
from app.services.detection.stoplists import (
    COMMON_WORDS,
    MEDICAL_TERMS,
    is_bd_location,
    is_country,
)
from app.services.memory import log_process_rss

logger = logging.getLogger("app.detection.presidio")

_lock = threading.Lock()
_analyzer: AnalyzerEngine | None = None
_load_count = 0

PRESIDIO_TO_TYPE: dict[str, str] = {
    "PERSON": "PERSON",
    "LOCATION": "LOCATION",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "URL": "URL",
    "IP_ADDRESS": "IP",
}

PRESIDIO_ENTITIES: list[str] = list(PRESIDIO_TO_TYPE.keys())

# Place-context cue directly before a Presidio LOCATION span on the same line (architecture.md §12)
LOCATION_CONTEXT_BEFORE_RE = regex.compile(
    r"(?i)(?:"
    r"\b(?:in|at|from|near|lives\s+in|living\s+in|resident\s+of|residing\s+in|located\s+in|"
    r"village|district|thana|upazila|division|city|town|road|house|area|address|residence)\b"
    r"|গ্রাম|থানা|উপজেলা|জেলা|ঠিকানা|এলাকা)"
    r"[\s:,/-]*$"
)


def _get_analyzer() -> AnalyzerEngine:
    global _analyzer, _load_count
    if _analyzer is not None:
        return _analyzer
    with _lock:
        if _analyzer is not None:
            return _analyzer
        model_name = get_settings().SPACY_MODEL
        provider = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": model_name}],
            }
        )
        nlp_engine = provider.create_engine()
        _analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
        _load_count += 1
        log_process_rss("presidio_loaded")
        return _analyzer


def _contains_medical_term(raw: str) -> bool:
    lowered = " ".join(raw.strip().lower().split())
    if lowered in MEDICAL_TERMS:
        return True
    tokens = re.findall(r"[A-Za-z0-9'-]+", lowered)
    return any(tok in MEDICAL_TERMS for tok in tokens)


def _contains_label_keyword(raw: str, text: str, end: int) -> bool:
    if is_label_keyword(raw):
        return True
    # Reject if span ends with ':' or is immediately followed by ':' / 'ঃ' (field label)
    if raw.rstrip().endswith((":", "ঃ")):
        return True
    tail = text[end : end + 3].lstrip(" \t")
    if tail.startswith((":", "ঃ")):
        return True
    tokens = re.findall(r"[A-Za-z0-9'-]+", raw.lower())
    return any(tok in LABEL_KEYWORDS for tok in tokens)


def _has_location_support(text: str, start: int, raw: str) -> bool:
    """Keep NLP LOCATION only when context supports a place or it matches built-in BD locations."""
    if is_bd_location(raw):
        return True
    # Inspect preceding text on the same line only (up to 35 chars)
    line_start = text.rfind("\n", 0, start) + 1
    window_start = max(line_start, start - 35)
    prefix = text[window_start:start]
    return bool(LOCATION_CONTEXT_BEFORE_RE.search(prefix))


def detect_presidio(text: str) -> list[Span]:
    if not text.strip():
        return []

    analyzer = _get_analyzer()
    results = analyzer.analyze(
        text=text,
        entities=PRESIDIO_ENTITIES,
        language="en",
        score_threshold=0.4,
    )

    spans: list[Span] = []
    for res in results:
        mapped = PRESIDIO_TO_TYPE.get(res.entity_type)
        if not mapped:
            continue
        raw_exact = text[res.start : res.end]
        raw = raw_exact.strip()
        if not raw:
            continue

        # Never allow Presidio spans to bridge across lines (prevents "Name\nMobile:" false merges)
        if "\n" in raw or "\r" in raw:
            continue

        # Filter 1: reject PERSON spans that are a single token (architecture.md §12)
        if mapped == "PERSON":
            words = [w for w in re.findall(r"[A-Za-z]+", raw)]
            if len(words) < 2:
                continue
            if all(w.lower() in COMMON_WORDS for w in words):
                continue

        # Filter 2: reject spans containing medical terms or clinical field label keywords
        if mapped in {"PERSON", "LOCATION"}:
            if _contains_medical_term(raw):
                continue
            if _contains_label_keyword(raw, text, res.end):
                continue

        # Filter 3: reject GPE/LOCATION that is a country (pycountry), and require place support
        if mapped == "LOCATION":
            if is_country(raw):
                continue
            if not _has_location_support(text, res.start, raw):
                continue

        # Filter 4: medical-unit guard on numeric spans
        if mapped == "PHONE" and has_adjacent_medical_unit(text, res.end):
            continue

        spans.append(
            Span(
                start=res.start,
                end=res.end,
                entity_type=mapped,
                score=round(float(res.score), 3),
                detector="presidio",
                rule_id=f"presidio.{res.entity_type.lower()}",
                reason=f"Local NLP/Presidio {res.entity_type} recognition",
            )
        )

    return spans
