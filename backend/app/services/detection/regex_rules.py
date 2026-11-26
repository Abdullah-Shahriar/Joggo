import re

from app.services.detection.base import Span, has_adjacent_medical_unit

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
URL_RE = re.compile(r"\bhttps?://[^\s<>\"'\)\]]+", re.IGNORECASE)
IPV4_RE = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
BD_MOBILE_RE = re.compile(r"(?<!\d)(?:\+?88[\s-]?)?01[3-9][\s-]?\d{2}[\s-]?\d{6}(?!\d)")
INTL_PHONE_RE = re.compile(r"(?<!\w)\+\d{1,3}[\s-]?\(?\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{3,4}(?!\d)")
NID_LABELLED_RE = re.compile(
    r"(?i)\b(?:NID|National\s*ID|NIN|SSN)\s*(?:No\.?|Number|#)?\s*[:#-]?\s*(\d{17}|\d{13}|\d{10}|\d{3}-\d{2}-\d{4})\b"
)
NID_STANDALONE_RE = re.compile(r"(?<![\d.])(\d{17}|\d{13})(?![\d.])")


def _is_valid_ipv4(raw: str) -> bool:
    parts = raw.split(".")
    if len(parts) != 4:
        return False
    return all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)


def detect_regex(text: str) -> list[Span]:
    spans: list[Span] = []

    for m in EMAIL_RE.finditer(text):
        spans.append(
            Span(
                start=m.start(),
                end=m.end(),
                entity_type="EMAIL",
                score=0.98,
                detector="regex",
                rule_id="regex.email",
                reason="Email address pattern",
            )
        )

    for m in URL_RE.finditer(text):
        end = m.end()
        while end > m.start() and text[end - 1] in ".,;:":
            end -= 1
        spans.append(
            Span(
                start=m.start(),
                end=end,
                entity_type="URL",
                score=0.95,
                detector="regex",
                rule_id="regex.url",
                reason="Web URL pattern",
            )
        )

    for m in IPV4_RE.finditer(text):
        if _is_valid_ipv4(m.group(0)):
            spans.append(
                Span(
                    start=m.start(),
                    end=m.end(),
                    entity_type="IP",
                    score=0.90,
                    detector="regex",
                    rule_id="regex.ipv4",
                    reason="IPv4 address pattern",
                )
            )

    for m in BD_MOBILE_RE.finditer(text):
        if not has_adjacent_medical_unit(text, m.end()):
            spans.append(
                Span(
                    start=m.start(),
                    end=m.end(),
                    entity_type="PHONE",
                    score=0.95,
                    detector="regex",
                    rule_id="regex.bd_mobile",
                    reason="Bangladesh mobile number pattern",
                )
            )

    for m in INTL_PHONE_RE.finditer(text):
        digits = "".join(ch for ch in m.group(0) if ch.isdigit())
        if len(digits) >= 10 and not has_adjacent_medical_unit(text, m.end()):
            spans.append(
                Span(
                    start=m.start(),
                    end=m.end(),
                    entity_type="PHONE",
                    score=0.90,
                    detector="regex",
                    rule_id="regex.intl_phone",
                    reason="International phone number pattern",
                )
            )

    for m in NID_LABELLED_RE.finditer(text):
        spans.append(
            Span(
                start=m.start(1),
                end=m.end(1),
                entity_type="ID",
                score=0.95,
                detector="regex",
                rule_id="regex.nid_labelled",
                reason="Labelled national ID / SSN",
            )
        )

    for m in NID_STANDALONE_RE.finditer(text):
        if not has_adjacent_medical_unit(text, m.end(1)):
            spans.append(
                Span(
                    start=m.start(1),
                    end=m.end(1),
                    entity_type="ID",
                    score=0.60,
                    detector="regex",
                    rule_id="regex.nid_standalone",
                    reason="Standalone 13/17-digit identifier",
                )
            )

    return spans
