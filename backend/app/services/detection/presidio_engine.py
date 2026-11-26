import logging
import re
import threading

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider

from app.config import get_settings
from app.services.detection.base import Span, has_adjacent_medical_unit
from app.services.detection.stoplists import COMMON_WORDS, MEDICAL_TERMS, is_country
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
    tokens = re.findall(r"[A-Za-z0-9'-]+", raw.lower())
    return any(tok in MEDICAL_TERMS for tok in tokens)


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
        raw = text[res.start : res.end].strip()
        if not raw:
            continue

        # Filter 1: reject PERSON spans that are a single token (architecture.md §12)
        if mapped == "PERSON":
            words = [w for w in re.findall(r"[A-Za-z]+", raw)]
            if len(words) < 2:
                continue
            if all(w.lower() in COMMON_WORDS for w in words):
                continue

        # Filter 2: reject spans where any token is in MEDICAL_TERMS
        if mapped in {"PERSON", "LOCATION"} and _contains_medical_term(raw):
            continue

        # Filter 3: reject GPE/LOCATION that is a country (pycountry)
        if mapped == "LOCATION" and is_country(raw):
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
