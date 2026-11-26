from datetime import datetime, timezone
import re
from typing import Any

from app.services.detection.base import TOKEN_PATTERN_RE, has_adjacent_medical_unit
from app.services.detection.dates import DATE_PATTERNS, detect_dates
from app.services.detection.labels import detect_labels
from app.services.detection.presidio_engine import detect_presidio
from app.services.detection.regex_rules import (
    BD_MOBILE_RE,
    EMAIL_RE,
    INTL_PHONE_RE,
    IPV4_RE,
    URL_RE,
    detect_regex,
)
from app.services.detection.stoplists import COMMON_WORDS, MEDICAL_TERMS

AGE_TOKEN_RE = re.compile(r"\b(?:Age\s+(?:\d{1,2}|90\+)|90\+\s+years)\b")
IMAGE_MARKER_RE = re.compile(r"\[IMAGE_TEXT p\d+\]")
TEN_PLUS_DIGITS_RE = re.compile(r"(?<!\d)\d{10,}(?!\d)")


def _mask_tokens_preserve_offsets(text: str) -> str:
    """Replace placeholders with same-length underscores so re-detection offsets stay exact."""
    chars = list(text)
    for pattern in (TOKEN_PATTERN_RE, AGE_TOKEN_RE, IMAGE_MARKER_RE):
        for m in pattern.finditer(text):
            for i in range(m.start(), m.end()):
                chars[i] = "_"
    return "".join(chars)


def _add_finding(
    findings: list[dict[str, Any]],
    seen: set[tuple[int, int, str]],
    *,
    ftype: str,
    reason: str,
    start: int,
    end: int,
) -> None:
    key = (start, end, ftype)
    if key in seen:
        return
    seen.add(key)
    findings.append(
        {
            "type": ftype,
            "reason": reason,
            "start": start,
            "end": end,
        }
    )


def run_safety_scan(
    *,
    sanitized_text: str,
    mapping: dict[str, str],
    name_components: list[str],
    entity_count: int,
    date_order: str | None = None,
    use_presidio: bool = True,
) -> dict[str, Any]:
    """Safety gate on sanitized text (architecture.md §14). Never stores real values in findings."""
    findings: list[dict[str, Any]] = []
    seen: set[tuple[int, int, str]] = set()
    warnings: list[str] = []

    # 4. Sanity check
    if len(sanitized_text.strip()) < 20:
        _add_finding(
            findings,
            seen,
            ftype="SANITY",
            reason="Sanitized text is too short to safely process",
            start=0,
            end=len(sanitized_text),
        )
    if entity_count == 0:
        warnings.append("NO_ENTITIES_FOUND")

    masked = _mask_tokens_preserve_offsets(sanitized_text)

    # 1. Literal leak check against Vault mapping values & name components (>= 3 chars)
    for tok, real_val in mapping.items():
        if tok.startswith("[DAY_"):
            continue
        cleaned = real_val.strip()
        if len(cleaned) < 3:
            continue
        if cleaned.lower() in COMMON_WORDS or cleaned.lower() in MEDICAL_TERMS:
            continue
        if any(ch.isdigit() for ch in cleaned):
            pat = re.compile(re.escape(cleaned), re.IGNORECASE)
        else:
            pat = re.compile(r"(?i)(?<!\w)" + re.escape(cleaned) + r"(?!\w)")
        for m in pat.finditer(masked):
            _add_finding(
                findings,
                seen,
                ftype="LEAK_LITERAL",
                reason="Previously detected identifier value still present in cleaned text",
                start=m.start(),
                end=m.end(),
            )

    for comp in name_components:
        if len(comp) < 3 or comp.lower() in COMMON_WORDS or comp.lower() in MEDICAL_TERMS:
            continue
        pat = re.compile(r"(?i)\b" + re.escape(comp) + r"\b")
        for m in pat.finditer(masked):
            _add_finding(
                findings,
                seen,
                ftype="LEAK_NAME_COMPONENT",
                reason="Name component still present in cleaned text",
                start=m.start(),
                end=m.end(),
            )

    # 2. Re-detection with detectors 1-4 on masked sanitized text (score >= 0.5)
    redetected = []
    redetected.extend(detect_regex(masked))
    redetected.extend(detect_labels(masked))
    redetected.extend(detect_dates(masked, date_order=date_order))
    if use_presidio:
        redetected.extend(detect_presidio(masked))

    for span in redetected:
        if span.score >= 0.5:
            _add_finding(
                findings,
                seen,
                ftype=span.entity_type,
                reason=f"Residual identifier detected ({span.rule_id})",
                start=span.start,
                end=span.end,
            )

    # 3. Direct pattern checks (email, URL, IPv4, 10+ digits, full date, phone)
    for m in EMAIL_RE.finditer(masked):
        _add_finding(findings, seen, ftype="EMAIL", reason="Residual email pattern", start=m.start(), end=m.end())
    for m in URL_RE.finditer(masked):
        _add_finding(findings, seen, ftype="URL", reason="Residual URL pattern", start=m.start(), end=m.end())
    for m in IPV4_RE.finditer(masked):
        _add_finding(findings, seen, ftype="IP", reason="Residual IPv4 pattern", start=m.start(), end=m.end())
    for m in TEN_PLUS_DIGITS_RE.finditer(masked):
        if not has_adjacent_medical_unit(masked, m.end()):
            _add_finding(
                findings,
                seen,
                ftype="ID",
                reason="Residual 10+ digit identifier sequence",
                start=m.start(),
                end=m.end(),
            )
    for m in BD_MOBILE_RE.finditer(masked):
        if not has_adjacent_medical_unit(masked, m.end()):
            _add_finding(findings, seen, ftype="PHONE", reason="Residual phone pattern", start=m.start(), end=m.end())
    for m in INTL_PHONE_RE.finditer(masked):
        digits = "".join(ch for ch in m.group(0) if ch.isdigit())
        if len(digits) >= 10 and not has_adjacent_medical_unit(masked, m.end()):
            _add_finding(findings, seen, ftype="PHONE", reason="Residual phone pattern", start=m.start(), end=m.end())
    for _rule_id, dpat in DATE_PATTERNS:
        for m in dpat.finditer(masked):
            _add_finding(findings, seen, ftype="DATE", reason="Residual date pattern", start=m.start(), end=m.end())

    findings.sort(key=lambda f: (f["start"], f["end"]))
    status = "PASS" if len(findings) == 0 else "BLOCK"

    return {
        "status": status,
        "findings": findings,
        "warnings": warnings,
        "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
