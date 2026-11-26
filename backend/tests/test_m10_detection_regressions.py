"""Phase 1 detection regression tests (synthetic data only, rules.md T4/P5)."""

import re

from app.services.detection.base import Span
from app.services.detection.resolve import normalize_person_name, run_detection
from app.services.safety import run_safety_scan
from app.services.tokenizer import tokenize_text


def _assert_one_token_per_normalized_name(mapping: dict[str, str]) -> None:
    """Invariant: within one document, the same normalized person name never maps to two tokens."""
    seen: dict[str, str] = {}
    for token, value in mapping.items():
        if not token.startswith(("[PATIENT_", "[DOCTOR_", "[PERSON_")):
            continue
        norm = normalize_person_name(value)
        if not norm:
            continue
        if norm in seen:
            assert seen[norm] == token, f"Normalized name {norm!r} mapped to both {seen[norm]} and {token}"
        else:
            seen[norm] = token


def test_dotted_dates_dob_labs_versions_and_safety_block() -> None:
    text = (
        "Patient Name: Nasrin Akter\n"
        "DOB: 02.07.1979\n"
        "Date of Admission: 12.10.2026\n"
        "Follow-up scheduled on 19.10.2026 (prior visit on 05.10.26).\n"
        "Labs: Creatinine 1.4 mg/dL, HbA1c 8.1 %, Hemoglobin 11.2 g/dL (Ref: 13.0 - 17.0).\n"
        "Device firmware v1.2.26 calibrated. Bare ratio 1.2.15 noted.\n"
    )
    spans = run_detection(text, date_order="DMY")
    tok = tokenize_text(text, spans)
    clean = tok.sanitized_text

    # Dotted DOB -> Age N (02.07.1979 to 12.10.2026 = 47)
    assert "02.07.1979" not in clean
    assert "Age 47" in clean

    # Dotted calendar dates -> [DAY_n] (including 2-digit dotted year with "on " context)
    assert "12.10.2026" not in clean
    assert "19.10.2026" not in clean
    assert "05.10.26" not in clean
    assert "[DAY_0]" in clean
    assert "[DAY_7]" in clean
    assert "[DAY_-7]" in clean

    # Lab decimals, reference ranges, version numbers, and contextless dotted tuples stay untouched
    assert "1.4 mg/dL" in clean
    assert "8.1 %" in clean
    assert "11.2 g/dL" in clean
    assert "13.0 - 17.0" in clean
    assert "v1.2.26" in clean
    assert "1.2.15" in clean

    # Clean document passes safety scan
    report_clean = run_safety_scan(
        sanitized_text=clean,
        mapping=tok.mapping,
        name_components=tok.name_components,
        entity_count=sum(tok.entity_summary.values()),
        date_order="DMY",
    )
    assert report_clean["status"] == "PASS", report_clean

    # Seeded leftover dotted date MUST BLOCK safety scan
    report_leaked = run_safety_scan(
        sanitized_text=clean + "\nDOB: 02.07.1979\n",
        mapping=tok.mapping,
        name_components=tok.name_components,
        entity_count=sum(tok.entity_summary.values()),
        date_order="DMY",
    )
    assert report_leaked["status"] == "BLOCK"
    assert any(f["type"] in {"DATE", "DOB"} for f in report_leaked["findings"])


def test_person_identity_consistency_relationships_metadata_and_no_location_mislabel() -> None:
    # Synthetic text mirroring sample_case_summary_2.pdf (no real people)
    text = (
        "Green Crescent Medical College\n"
        "Case Summary\n"
        "Patient Name: Nasrin Akter\n"
        "DOB: 02.07.1979\n"
        "Date of Admission: 12.10.2026\n"
        "Mobile: 01711-223344\n"
        "Spouse: Tareq Hasan\n"
        "Address: Sylhet\n"
        "\n"
        "History:\n"
        "Nasrin, a 47-year-old teacher, presented with hyperglycemia and fever.\n"
        "Nasrin Akter's home glucose logs showed poor control.\n"
        "Her husband Tareq and sister Ruma accompanied her to the ward.\n"
        "Neighbour Jamal brought her prior medication list from Sylhet.\n"
        "\n"
        "Prepared for: Nasrin Akter\n"
    )

    spans = run_detection(text, metadata_hints=["Nasrin Akter"], date_order="DMY")
    tok = tokenize_text(text, spans)
    clean = tok.sanitized_text

    # No real names left behind
    for secret in ("Nasrin Akter", "Nasrin", "Tareq Hasan", "Tareq", "Ruma", "Jamal"):
        assert secret not in clean, f"Leaked {secret!r} in:\n{clean}"

    # "Nasrin", "Nasrin Akter", "Nasrin Akter's", and metadata author footer all become [PATIENT_A]
    assert clean.count("[PATIENT_A]") == 4, f"Expected 4 occurrences of [PATIENT_A], got:\n{clean}"
    assert "[OTHER_" not in clean, f"Metadata hint should reuse [PATIENT_A], not OTHER:\n{clean}"

    # Known people are NEVER labelled as LOCATION
    for token, val in tok.mapping.items():
        if token.startswith("[LOCATION_"):
            low = val.lower()
            assert "nasrin" not in low and "tareq" not in low and "ruma" not in low and "jamal" not in low

    # "husband Tareq", "sister Ruma", "neighbour Jamal" each become a PERSON token
    assert re.search(r"husband\s+\[PERSON_\d+\]", clean), clean
    assert re.search(r"sister\s+\[PERSON_\d+\]", clean), clean
    assert re.search(r"Neighbour\s+\[PERSON_\d+\]", clean), clean

    # "Spouse: Tareq Hasan" and "husband Tareq" share the exact same PERSON token
    spouse_match = re.search(r"Spouse:\s*(\[PERSON_\d+\])", clean)
    husband_match = re.search(r"husband\s+(\[PERSON_\d+\])", clean)
    assert spouse_match and husband_match
    assert spouse_match.group(1) == husband_match.group(1)

    # Genuine Bangladesh place ("Sylhet") is still detected as LOCATION
    assert "[LOCATION_" in clean
    assert "Sylhet" not in clean

    # Invariant: no duplicate adjacent identical tokens & one token per normalized name
    assert not re.search(r"(\[[A-Z_0-9]+\])\s+\1", clean), f"Duplicate adjacent token in:\n{clean}"
    _assert_one_token_per_normalized_name(tok.mapping)

    report = run_safety_scan(
        sanitized_text=clean,
        mapping=tok.mapping,
        name_components=tok.name_components,
        entity_count=sum(tok.entity_summary.values()),
        date_order="DMY",
    )
    assert report["status"] == "PASS", report


def test_medical_scales_terms_and_label_keywords_never_tokenized() -> None:
    # Synthetic text mirroring sample_discharge_summary.pdf clinical scales and adjacent labels
    text = (
        "City Care Hospital\n"
        "Discharge Summary\n"
        "Patient Name: Karim Uddin\n"
        "DOB: 04.03.1975\n"
        "Date of Admission: 10.10.2026\n"
        "Spouse: Tareq Hasan\n"
        "Mobile: 01812-345678\n"
        "Consultant: Dr. Farhana Islam\n"
        "Ward: Medicine Ward 4, ICU step-down to HDU\n"
        "\n"
        "Neurology & Endocrine:\n"
        "On admission Glasgow Coma Scale 15, GCS 15, APGAR N/A, CURB-65 score 1.\n"
        "Started on insulin sliding scale and monitored in OPD after discharge.\n"
        "NYHA class II, Child-Pugh A, Wells score 0, Braden 19, Morse 15, Barthel 95, MMSE 29, VAS 2, NEWS 1, qSOFA 0, SOFA 1, ECOG 1, Karnofsky 90, BMI 24.5, SpO2 98 %.\n"
        "Emergency Contact: Tareq Hasan, Mobile: 01812-345678\n"
    )

    spans = run_detection(text, metadata_hints=["Karim Uddin"], date_order="DMY")
    tok = tokenize_text(text, spans)
    clean = tok.sanitized_text

    # Clinical terms, scales, and field labels MUST remain untouched
    for preserved in (
        "insulin sliding scale",
        "Glasgow Coma Scale 15",
        "GCS 15",
        "Mobile:",
        "Ward:",
        "Consultant:",
        "ICU",
        "HDU",
        "OPD",
        "CURB-65",
        "NYHA",
        "Child-Pugh",
        "Wells",
        "Braden",
        "Morse",
        "Barthel",
        "MMSE",
        "VAS",
        "NEWS",
        "qSOFA",
        "SOFA",
        "ECOG",
        "Karnofsky",
        "BMI 24.5",
        "SpO2 98 %",
    ):
        assert preserved in clean, f"Expected {preserved!r} to stay untouched in:\n{clean}"

    # Real identifiers still removed
    for secret in ("Karim Uddin", "04.03.1975", "10.10.2026", "Tareq Hasan", "01812-345678", "Farhana Islam"):
        assert secret not in clean

    assert not re.search(r"(\[[A-Z_0-9]+\])\s+\1", clean)
    _assert_one_token_per_normalized_name(tok.mapping)

    report = run_safety_scan(
        sanitized_text=clean,
        mapping=tok.mapping,
        name_components=tok.name_components,
        entity_count=sum(tok.entity_summary.values()),
        date_order="DMY",
    )
    assert report["status"] == "PASS", report


def test_adjacent_identical_tokens_merged_into_single_token() -> None:
    text = "Spouse: Tareq Hasan was present."
    # Simulate two adjacent spans pointing to the exact same canonical person
    spans = [
        Span(8, 13, "PERSON", 0.9, "sweep", "sweep.name_component", "comp 1", source="sweep", parent_value="Tareq Hasan"),
        Span(14, 19, "PERSON", 0.9, "sweep", "sweep.name_component", "comp 2", source="sweep", parent_value="Tareq Hasan"),
    ]
    tok = tokenize_text(text, spans)
    assert tok.sanitized_text == "Spouse: [PERSON_1] was present."
    assert "[PERSON_1] [PERSON_1]" not in tok.sanitized_text
    assert tok.entity_rows[0].occurrences == 1


def test_bangla_dotted_dates_and_relationship_context() -> None:
    text = (
        "ভর্তির তারিখ: ১২.১০.২০২৬\n"
        "রোগীর নাম: নাসরিন আক্তার\n"
        "জন্ম তারিখ: ০২.০৭.১৯৭৯\n"
        "মোবাইল: ০১৭১১-২২৩৩৪৪\n"
        "তার স্বামী তারেক এবং বোন রুমা হাসপাতালে এসেছিলেন। প্রতিবেশী জামাল সাহায্য করেন।\n"
        "পরবর্তী ভিজিট ১৯.১০.২০২৬।\n"
    )

    spans = run_detection(text, metadata_hints=["নাসরিন আক্তার"], date_order="DMY")
    tok = tokenize_text(text, spans)
    clean = tok.sanitized_text

    assert "Age 47" in clean
    assert "[DAY_0]" in clean
    assert "[DAY_7]" in clean
    assert "[PATIENT_A]" in clean
    assert "মোবাইল:" in clean

    for secret in ("নাসরিন আক্তার", "নাসরিন", "তারেক", "রুমা", "জামাল", "০২.০৭.১৯৭৯", "১২.১০.২০২৬", "১৯.১০.২০২৬", "০১৭১১-২২৩৩৪৪"):
        assert secret not in clean, f"Expected Bangla identifier {secret!r} to be redacted in:\n{clean}"

    assert re.search(r"স্বামী\s+\[PERSON_\d+\]", clean), clean
    assert re.search(r"বোন\s+\[PERSON_\d+\]", clean), clean
    assert re.search(r"প্রতিবেশী\s+\[PERSON_\d+\]", clean), clean
    assert not re.search(r"(\[[A-Z_0-9]+\])\s+\1", clean)
    _assert_one_token_per_normalized_name(tok.mapping)

    report = run_safety_scan(
        sanitized_text=clean,
        mapping=tok.mapping,
        name_components=tok.name_components,
        entity_count=sum(tok.entity_summary.values()),
        date_order="DMY",
    )
    assert report["status"] == "PASS", report
