from app.models.document import TaskType

SYSTEM_PROMPT = (
    "You are a clinical documentation assistant. The text contains placeholders such as "
    "[PATIENT_A], [DOCTOR_1], [DAY_3]. Copy placeholders exactly as written. Never guess or "
    "invent identities, dates or numbers. [DAY_0] is the admission or first recorded date; "
    "[DAY_n] means n days after it. Write only what the text supports; write 'Not documented' "
    "otherwise. Output Markdown with exactly these headings."
)

AI_DISCLAIMER = "_AI-generated draft. Must be reviewed by a licensed clinician before use._"

TASK_HEADINGS: dict[TaskType, list[str]] = {
    TaskType.discharge_summary: [
        "Diagnosis",
        "Clinical course",
        "Key findings",
        "Medications at discharge",
        "Follow-up",
    ],
    TaskType.case_summary: [
        "Summary",
        "Key findings",
        "Concerns",
    ],
    TaskType.treatment_plan: [
        "Assessment",
        "Plan",
        "Monitoring",
        "Follow-up",
    ],
}


def build_user_prompt(task_type: TaskType, sanitized_text: str, *, repair: bool = False) -> str:
    """Build outbound LLM user message using ONLY static task instructions + sanitized_text (rules.md P3)."""
    headings = TASK_HEADINGS[task_type]
    headings_md = "\n".join(f"## {h}" for h in headings)
    parts = [
        f"Task: {task_type.value.replace('_', ' ')}",
        "Required Markdown headings:",
        headings_md,
        "",
        "Clinical text (de-identified):",
        sanitized_text,
    ]
    if repair:
        parts.append("")
        parts.append("Return only the required Markdown headings")
    return "\n".join(parts)


TASK_LABELS: dict[TaskType, str] = {
    TaskType.discharge_summary: "discharge summary",
    TaskType.case_summary: "case summary",
    TaskType.treatment_plan: "treatment plan",
}


def build_external_handoff_prompt(task_type: TaskType, sanitized_text: str) -> str:
    """Build privacy-safe external chat handoff prompt using ONLY static instructions + sanitized_text (P3)."""
    headings_md = "\n".join(f"## {h}" for h in TASK_HEADINGS[task_type])
    return "\n".join(
        [
            f"Write a structured {TASK_LABELS[task_type]} using only the privacy-safe clinical text below.",
            "Copy all placeholders (such as [PATIENT_A], [DOCTOR_1], [DAY_0]) exactly as written and never guess or invent missing details.",
            "",
            "Required headings:",
            headings_md,
            "",
            "Clinical text (de-identified):",
            sanitized_text.strip(),
        ]
    )
