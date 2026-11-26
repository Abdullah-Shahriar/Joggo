"""Manual smoke script to verify real Gemini/Groq API connectivity using synthetic tokens only."""

from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
for root in (SCRIPT_DIR.parent / "backend", SCRIPT_DIR.parent):
    if (root / "app").is_dir() and str(root) not in sys.path:
        sys.path.insert(0, str(root))

from app.models.document import TaskType
from app.services.llm.router import LLMRouterError, route_generate

SYNTHETIC_CLEAN_TEXT = (
    "Patient Name: [PATIENT_A]\n"
    "DOB: Age 58\n"
    "Date of Admission: [DAY_0]\n"
    "Discharge Date: [DAY_5]\n"
    "Consultant: [DOCTOR_1]\n"
    "Diagnosis: Community-acquired pneumonia, resolved.\n"
    "Treatment: Ceftriaxone 1000 mg IV daily. Hemoglobin 13.4 g/dL.\n"
    "Follow-up: Review with [DOCTOR_1] on [DAY_14].\n"
)


def main() -> None:
    try:
        outcome = route_generate(TaskType.discharge_summary, SYNTHETIC_CLEAN_TEXT)
    except LLMRouterError as exc:
        print(f"Smoke test failed: {exc.failure_code.value}")
        for item in exc.history:
            print(f"  provider={item.provider} attempts={item.attempts} error={item.error_code}")
        sys.exit(1)

    print(
        f"Smoke test passed: provider={outcome.result.provider} "
        f"model={outcome.result.model} latency_ms={outcome.result.latency_ms} "
        f"fallback={outcome.used_fallback} chars={len(outcome.result.text)}"
    )


if __name__ == "__main__":
    main()
