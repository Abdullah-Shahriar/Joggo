import regex

from app.services.detection.base import (
    Span,
    UNICODE_WORD_BOUNDARY_LEFT,
    UNICODE_WORD_BOUNDARY_RIGHT,
    has_adjacent_medical_unit,
)
from app.services.detection.stoplists import (
    BANGLA_STOPWORDS,
    COMMON_WORDS,
    MEDICAL_TERMS,
    is_bd_location,
    is_country,
)

# Label specifications from architecture.md §12 (English + Bangla).
LABEL_GROUPS: list[tuple[str, list[str], float, bool]] = [
    (
        "PATIENT",
        ["Patient Name", "Name of Patient", "Pt Name", "Patient", "রোগীর নাম"],
        0.96,
        False,
    ),
    (
        "DOCTOR",
        [
            "Consultant",
            "Doctor",
            "Physician",
            "Attending",
            "Surgeon",
            "Referred by",
            "Signed by",
            "Reported by",
            "Verified by",
            "Pathologist",
            "Technologist",
            "ডাক্তার",
            "চিকিৎসক",
            "পরামর্শক",
        ],
        0.94,
        False,
    ),
    (
        "PERSON",
        [
            "Father's Name",
            "Mother's Name",
            "Spouse",
            "Husband",
            "Wife",
            "Guardian",
            "Next of Kin",
            "Informant",
            "Relative",
            "Family contact",
            "পিতার নাম",
            "মাতার নাম",
            "স্বামীর নাম",
            "স্ত্রীর নাম",
            "অভিভাবক",
        ],
        0.92,
        False,
    ),
    (
        "MRN",
        [
            "MRN",
            "UHID",
            "Hospital No",
            "Registration No",
            "Reg No",
            "Patient ID",
            "Case No",
            "File No",
            "Visit No",
            "Accession No",
            "Lab ID",
            "Lab No",
            "রেজিস্ট্রেশন নং",
            "রেজি নং",
            "হাসপাতাল নং",
        ],
        0.96,
        False,
    ),
    (
        "ID",
        [
            "NID",
            "National ID",
            "NIN",
            "Passport",
            "License No",
            "Policy No",
            "Insurance ID",
            "Member ID",
            "Account No",
            "Card No",
            "Serial",
            "S/N",
            "Device ID",
            "IMEI",
            "VIN",
            "Plate",
            "এনআইডি",
            "জাতীয় পরিচয়পত্র",
            "পাসপোর্ট",
        ],
        0.95,
        False,
    ),
    (
        "PHONE",
        [
            "Emergency Contact",
            "Tel",
            "Phone",
            "Mobile",
            "Cell",
            "Contact",
            "Fax",
            "মোবাইল",
            "ফোন",
            "যোগাযোগ",
        ],
        0.94,
        False,
    ),
    (
        "LOCATION",
        [
            "Permanent Address",
            "Present Address",
            "Address",
            "Residence",
            "Village",
            "Thana",
            "Upazila",
            "District",
            "Postal Code",
            "ZIP",
            "বর্তমান ঠিকানা",
            "স্থায়ী ঠিকানা",
            "ঠিকানা",
            "গ্রাম",
            "থানা",
            "উপজেলা",
            "জেলা",
        ],
        0.92,
        True,
    ),
    (
        "EMAIL",
        ["Email", "E-mail"],
        0.96,
        False,
    ),
]


def _build_label_keyword_sets() -> tuple[frozenset[str], frozenset[str]]:
    """Build exact label-key phrases and single-word label keywords (English & Bangla) that must never be tokenized."""
    phrases: set[str] = {
        "name",
        "নাম",
        "dob",
        "d.o.b",
        "date of birth",
        "birth date",
        "date of admission",
        "admission date",
        "discharge date",
        "date of visit",
        "date of report",
        "date of collection",
        "জন্ম তারিখ",
        "ভর্তির তারিখ",
        "ward",
        "unit",
        "bed",
        "department",
        "age",
        "sex",
        "gender",
    }
    words: set[str] = {
        "name",
        "নাম",
        "dob",
        "ward",
        "unit",
        "bed",
        "department",
        "age",
        "sex",
        "gender",
        "mobile",
        "phone",
        "contact",
        "address",
        "consultant",
        "doctor",
        "physician",
        "attending",
        "surgeon",
        "pathologist",
        "technologist",
        "patient",
        "spouse",
        "husband",
        "wife",
        "guardian",
        "informant",
        "relative",
        "mrn",
        "uhid",
        "nid",
        "nin",
        "passport",
        "email",
        "e-mail",
        "tel",
        "cell",
        "fax",
        "residence",
        "village",
        "thana",
        "upazila",
        "district",
        "zip",
        "serial",
        "imei",
        "vin",
        "plate",
    }
    for _etype, keys, _score, _cont in LABEL_GROUPS:
        for k in keys:
            low = k.strip().lower()
            phrases.add(low)
            parts = low.split()
            if len(parts) == 1:
                words.add(low)
    return frozenset(phrases), frozenset(words)


LABEL_KEYWORD_PHRASES, LABEL_KEYWORDS = _build_label_keyword_sets()


def is_label_keyword(raw: str) -> bool:
    cleaned = " ".join(raw.strip().rstrip(":ঃ-.,;").lower().split())
    if not cleaned:
        return False
    return cleaned in LABEL_KEYWORD_PHRASES or cleaned in LABEL_KEYWORDS


# Inline label keys that terminate a preceding label value on the same line
_ALL_INLINE_STOP_KEYS = sorted(
    {k for _et, ks, _sc, _c in LABEL_GROUPS for k in ks}
    | {"DOB", "D.O.B", "Age", "Sex", "Gender", "Ward", "Unit", "Bed", "Date", "জন্ম তারিখ", "ভর্তির তারিখ"},
    key=len,
    reverse=True,
)
INLINE_LABEL_STOP_RE = regex.compile(
    r"(?i)(?:[ \t,;(]+)"
    + r"(?:"
    + "|".join(regex.escape(k) for k in _ALL_INLINE_STOP_KEYS)
    + r")\s*[:ঃ]"
)

BARE_NAME_EXCLUDED_PREFIXES = (
    "test name",
    "drug name",
    "medicine name",
    "generic name",
    "brand name",
)

# Title prefixes using Unicode letter classes, strictly same-line ([ \t], never crossing \n)
DOCTOR_TITLE_RE = regex.compile(
    r"\b(?:Dr|Prof|Professor)\.?[ \t]+(\p{Lu}\p{L}*(?:[ \t'-]\p{Lu}\p{L}*){0,3})\b"
)
PERSON_TITLE_RE = regex.compile(
    r"\b(?:Mr|Mrs|Ms|Md|Mst)\.?[ \t]+(\p{Lu}\p{L}*(?:[ \t'-]\p{Lu}\p{L}*){0,3})\b"
)

# Relationship context -> PERSON (1-3 capitalized words directly after relationship keyword, same line)
EN_RELATIONSHIP_RE = regex.compile(
    r"(?i:\b(?:husband|wife|son|daughter|sister|brother|mother|father|neighbou?r|uncle|aunt|cousin|friend|guardian)\b)"
    r"(?:,[ \t]+|[ \t]+)"
    r"(\p{Lu}\p{L}*(?:[ \t'-]\p{Lu}\p{L}*){0,2})\b"
)

BANGLA_RELATIONSHIP_RE = regex.compile(
    UNICODE_WORD_BOUNDARY_LEFT
    + r"(?:স্বামী|স্ত্রী|ছেলে|মেয়ে|বোন|ভাই|মা|বাবা|প্রতিবেশী)"
    + r"(?:,[ \t]+|[ \t]+)"
    + r"([\p{L}\p{M}]+(?:[ \t]+[\p{L}\p{M}]+){0,2})"
    + UNICODE_WORD_BOUNDARY_RIGHT
)

# Possessive 's context -> PERSON (1-3 capitalized words directly before 's / ’s)
POSSESSIVE_PERSON_RE = regex.compile(
    r"\b(\p{Lu}\p{L}*(?:[ \t'-]\p{Lu}\p{L}*){0,2})(?=['’]s\b)"
)

# Age-description context -> PERSON (1-3 capitalized words followed by "is a N-year-old" or ", a N-year-old")
AGE_DESC_PERSON_RE = regex.compile(
    r"\b(\p{Lu}\p{L}*(?:[ \t'-]\p{Lu}\p{L}*){0,2})"
    r"(?=[ \t]+(?i:is)[ \t]+(?i:an?)[ \t]+\d{1,3}[- ]year[- ]old\b|,[ \t]+(?i:an?)[ \t]+\d{1,3}[- ]year[- ]old\b)"
)

# Bangla title prefixes (same-line 1-4 words; trimmed at stopwords/punctuation).
BANGLA_DOCTOR_TITLE_RE = regex.compile(
    UNICODE_WORD_BOUNDARY_LEFT
    + r"(?:ডাঃ|ডা\.)[ \t]+([\p{L}\p{M}]+(?:[ \t]+[\p{L}\p{M}]+){0,3})"
    + UNICODE_WORD_BOUNDARY_RIGHT
)
BANGLA_PERSON_TITLE_RE = regex.compile(
    UNICODE_WORD_BOUNDARY_LEFT
    + r"(?:জনাব|মোছাঃ|মোছা\.|মোঃ|মো\.|বেগম|শ্রীমতী|শ্রী)[ \t]+([\p{L}\p{M}]+(?:[ \t]+[\p{L}\p{M}]+){0,3})"
    + UNICODE_WORD_BOUNDARY_RIGHT
)

# Facility names (Title Case or ALL CAPS for OCR clinic headers; strictly same-line)
FACILITY_RE = regex.compile(
    r"\b((?:[\p{Lu}][\p{L}&'-]*[ \t]+){1,5}"
    r"(?:Medical[ \t]+College|Health[ \t]+Cent(?:er|re)|Diagnostic[ \t]+(?:Cent(?:er|re)|Lab)|"
    r"Hospital|Clinic|Diagnostic|Laboratory|Lab|Institute))\b",
    regex.IGNORECASE,
)


def _trim_label_value(raw_rest: str) -> tuple[int, int]:
    """Return (rel_start, rel_end) for label value stopping at '|', 3+ spaces, or inline 'Key:', max 80 chars."""
    leading_ws = len(raw_rest) - len(raw_rest.lstrip(" \t"))
    val = raw_rest[leading_ws:]
    cut = len(val)

    pipe_idx = val.find("|")
    if pipe_idx != -1:
        cut = min(cut, pipe_idx)

    multi_space = regex.search(r" {3,}", val)
    if multi_space:
        cut = min(cut, multi_space.start())

    inline_lbl = INLINE_LABEL_STOP_RE.search(val)
    if inline_lbl:
        cut = min(cut, inline_lbl.start())

    cut = min(cut, 80)
    sliced = val[:cut].rstrip(" \t.,;।(")
    return leading_ws, leading_ws + len(sliced)


def _has_alnum(s: str) -> bool:
    return bool(regex.search(r"[\p{L}\p{N}]", s))


def _trim_english_name_span(text: str, group_start: int, group_text: str) -> tuple[int, int] | None:
    """Trim an English capitalized name candidate at the first stopword, medical term, or label keyword."""
    kept_end: int | None = None
    kept_words: list[str] = []
    for wm in regex.finditer(r"[\p{L}'-]+", group_text):
        word = wm.group(0)
        low = word.lower().strip(".,'")
        # Stop if this word is followed by ':' (it is a label key on the same line)
        after_pos = group_start + wm.end()
        tail = text[after_pos : after_pos + 3].lstrip(" \t")
        if tail.startswith(":") or tail.startswith("ঃ"):
            break
        if (
            low in MEDICAL_TERMS
            or low in COMMON_WORDS
            or is_label_keyword(word)
            or is_country(word)
            or is_bd_location(word)
        ):
            break
        kept_words.append(word)
        kept_end = after_pos
    if kept_end is None or not kept_words:
        return None
    full_phrase = " ".join(kept_words).lower()
    if full_phrase in MEDICAL_TERMS or is_label_keyword(full_phrase) or is_bd_location(full_phrase):
        return None
    return group_start, kept_end


def _trim_bangla_title_words(text: str, match_start: int, group_start: int, group_text: str) -> int | None:
    """Return end offset for a Bangla title/relationship match, stopping before clinical/sentence stopwords."""
    kept_end: int | None = None
    for wm in regex.finditer(r"[\p{L}\p{M}]+", group_text):
        word = wm.group(0)
        low = word.lower().strip(".,'")
        after_pos = group_start + wm.end()
        tail = text[after_pos : after_pos + 3].lstrip(" \t")
        if tail.startswith(":") or tail.startswith("ঃ"):
            break
        if word in BANGLA_STOPWORDS or low in MEDICAL_TERMS or is_label_keyword(word):
            break
        kept_end = after_pos
    if kept_end is None or kept_end <= match_start:
        return None
    return kept_end


def _all_words_capitalized_or_upper(phrase: str) -> bool:
    words = [w for w in phrase.split() if w]
    if not words:
        return False
    lowered = phrase.lower()
    if lowered in {"clinical laboratory", "clinical lab", "medical report"}:
        return False
    cap_count = sum(1 for w in words if w[0].isupper())
    return cap_count == len(words)


def detect_labels(text: str) -> list[Span]:
    spans: list[Span] = []
    lines = text.splitlines(keepends=True)
    offset = 0

    # Precompile line-level patterns for each label group (accepting ':', 'ঃ', and '-')
    compiled_groups: list[tuple[str, regex.Pattern[str], float, bool]] = []
    for entity_type, keys, score, allow_continuation in LABEL_GROUPS:
        escaped = sorted((regex.escape(k) for k in keys), key=len, reverse=True)
        pat = regex.compile(
            r"(?i)" + UNICODE_WORD_BOUNDARY_LEFT + r"(" + "|".join(escaped) + r")\s*[:ঃ\-]+\s*(.*)$"
        )
        compiled_groups.append((entity_type, pat, score, allow_continuation))

    bare_name_re = regex.compile(r"(?i)^\s*(Name|নাম)\s*[:ঃ]+\s*(.*)$")

    for idx, line in enumerate(lines):
        line_no_nl = line.rstrip("\r\n")
        line_lower = line_no_nl.lstrip().lower()

        # Bare 'Name:' / 'নাম:' only at line start, excluding Test/Drug/Medicine/Generic/Brand Name
        if not any(line_lower.startswith(p) for p in BARE_NAME_EXCLUDED_PREFIXES):
            m_bare = bare_name_re.match(line_no_nl)
            if m_bare:
                rest = m_bare.group(2)
                r_start, r_end = _trim_label_value(rest)
                val = rest[r_start:r_end]
                if val and _has_alnum(val) and not is_label_keyword(val):
                    abs_start = offset + m_bare.start(2) + r_start
                    abs_end = offset + m_bare.start(2) + r_end
                    spans.append(
                        Span(
                            start=abs_start,
                            end=abs_end,
                            entity_type="PATIENT",
                            score=0.90,
                            detector="labels",
                            rule_id="label.bare_name",
                            reason=f"Label '{m_bare.group(1)}:' at line start",
                        )
                    )

        for entity_type, pat, score, allow_continuation in compiled_groups:
            m = pat.search(line_no_nl)
            if not m:
                continue
            key_text = m.group(1)
            rest = m.group(2)

            # Avoid matching "Patient:" followed by a long clinical sentence
            if key_text.lower() == "patient" and len(rest.strip().split()) > 5:
                continue

            r_start, r_end = _trim_label_value(rest)
            val = rest[r_start:r_end]
            if not val or not _has_alnum(val) or is_label_keyword(val):
                continue

            # For PHONE/ID labels, ensure medical-unit guard doesn't swallow a clinical value
            abs_start = offset + m.start(2) + r_start
            abs_end = offset + m.start(2) + r_end
            if entity_type in {"PHONE", "ID", "MRN"} and has_adjacent_medical_unit(text, abs_end):
                continue

            # Continuation line for Address / ঠিকানা (architecture.md §12)
            if (
                allow_continuation
                and (key_text.lower().endswith("address") or key_text.endswith("ঠিকানা"))
                and (idx + 1) < len(lines)
            ):
                next_line = lines[idx + 1].rstrip("\r\n")
                next_stripped = next_line.strip()
                if (
                    next_stripped
                    and ":" not in next_stripped
                    and "ঃ" not in next_stripped
                    and len(next_stripped) < 80
                    and not set(next_stripped).issubset({"-", "_", "="})
                    and not next_stripped.startswith("[IMAGE_TEXT")
                ):
                    abs_end = offset + len(line) + len(next_line.rstrip())

            spans.append(
                Span(
                    start=abs_start,
                    end=abs_end,
                    entity_type=entity_type,
                    score=score,
                    detector="labels",
                    rule_id=f"label.{entity_type.lower()}",
                    reason=f"Label '{key_text}:' + value",
                )
            )

        offset += len(line)

    # English title prefix rules (same-line, trimmed before medical/label words)
    for m in DOCTOR_TITLE_RE.finditer(text):
        trimmed = _trim_english_name_span(text, m.start(1), m.group(1))
        if trimmed is None:
            continue
        spans.append(
            Span(
                start=m.start(),
                end=trimmed[1],
                entity_type="DOCTOR",
                score=0.92,
                detector="labels",
                rule_id="title.doctor",
                reason="Doctor title prefix (Dr/Prof)",
            )
        )

    for m in PERSON_TITLE_RE.finditer(text):
        trimmed = _trim_english_name_span(text, m.start(1), m.group(1))
        if trimmed is None:
            continue
        spans.append(
            Span(
                start=m.start(),
                end=trimmed[1],
                entity_type="PERSON",
                score=0.86,
                detector="labels",
                rule_id="title.person",
                reason="Honorific title prefix (Mr/Mrs/Ms/Md/Mst)",
            )
        )

    # English relationship context -> PERSON (e.g. "husband Tareq", "sister Ruma", "neighbour Jamal")
    for m in EN_RELATIONSHIP_RE.finditer(text, overlapped=True):
        trimmed = _trim_english_name_span(text, m.start(1), m.group(1))
        if trimmed is None:
            continue
        spans.append(
            Span(
                start=trimmed[0],
                end=trimmed[1],
                entity_type="PERSON",
                score=0.90,
                detector="labels",
                rule_id="context.person_relationship",
                reason="Person name following relationship keyword",
            )
        )

    # Bangla relationship context -> PERSON (e.g. "স্বামী তারেক", "বোন রুমা", "প্রতিবেশী জামাল")
    for m in BANGLA_RELATIONSHIP_RE.finditer(text, overlapped=True):
        end_pos = _trim_bangla_title_words(text, m.start(1), m.start(1), m.group(1))
        if end_pos is None or end_pos <= m.start(1):
            continue
        spans.append(
            Span(
                start=m.start(1),
                end=end_pos,
                entity_type="PERSON",
                score=0.90,
                detector="labels",
                rule_id="context.person_relationship_bn",
                reason="Bangla person name following relationship keyword",
            )
        )

    # Possessive 's context -> PERSON (e.g. "Nasrin Akter's", "Tareq's")
    for m in POSSESSIVE_PERSON_RE.finditer(text):
        trimmed = _trim_english_name_span(text, m.start(1), m.group(1))
        if trimmed is None or trimmed[1] != m.end(1):
            continue
        spans.append(
            Span(
                start=trimmed[0],
                end=trimmed[1],
                entity_type="PERSON",
                score=0.84,
                detector="labels",
                rule_id="context.person_possessive",
                reason="Capitalized person name before possessive 's",
            )
        )

    # Age-description context -> PERSON (e.g. "Nasrin, a 47-year-old", "Tareq is a 50-year-old")
    for m in AGE_DESC_PERSON_RE.finditer(text):
        trimmed = _trim_english_name_span(text, m.start(1), m.group(1))
        if trimmed is None or trimmed[1] != m.end(1):
            continue
        spans.append(
            Span(
                start=trimmed[0],
                end=trimmed[1],
                entity_type="PERSON",
                score=0.88,
                detector="labels",
                rule_id="context.person_age_desc",
                reason="Capitalized person name before age description",
            )
        )

    # Bangla title prefix rules
    for m in BANGLA_DOCTOR_TITLE_RE.finditer(text):
        end_pos = _trim_bangla_title_words(text, m.start(), m.start(1), m.group(1))
        if end_pos is None:
            continue
        spans.append(
            Span(
                start=m.start(),
                end=end_pos,
                entity_type="DOCTOR",
                score=0.92,
                detector="labels",
                rule_id="title.doctor_bn",
                reason="Bangla doctor title prefix",
            )
        )

    for m in BANGLA_PERSON_TITLE_RE.finditer(text):
        end_pos = _trim_bangla_title_words(text, m.start(), m.start(1), m.group(1))
        if end_pos is None:
            continue
        spans.append(
            Span(
                start=m.start(),
                end=end_pos,
                entity_type="PERSON",
                score=0.86,
                detector="labels",
                rule_id="title.person_bn",
                reason="Bangla honorific title prefix",
            )
        )

    # Facility names
    for m in FACILITY_RE.finditer(text):
        phrase = m.group(1).strip()
        if not _all_words_capitalized_or_upper(phrase):
            continue
        spans.append(
            Span(
                start=m.start(1),
                end=m.start(1) + len(phrase),
                entity_type="FACILITY",
                score=0.88,
                detector="labels",
                rule_id="facility.name",
                reason="Healthcare facility name pattern",
            )
        )

    return spans
