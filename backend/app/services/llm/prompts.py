from app.models.document import TaskType

SYSTEM_PROMPT = (
    "You are a clinical documentation assistant. The text contains placeholders such as "
    "[PATIENT_A], [DOCTOR_1], [DAY_3]. Copy placeholders exactly as written. Never guess or "
    "invent identities, dates or numbers. [DAY_0] is the admission or first recorded date; "
    "[DAY_n] means n days after it. Write only what the text supports, synthesizing documented "
    "findings under each heading as guided; write 'Not documented' under a heading only when "
    "the record contains nothing relevant to that section. Output Markdown with only the "
    "required headings."
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

TASK_HEADING_GUIDANCE: dict[TaskType, list[tuple[str, str]]] = {
    TaskType.discharge_summary: [
        (
            "Diagnosis",
            "primary and secondary diagnoses or working clinical impressions supported by the record.",
        ),
        (
            "Clinical course",
            "chronological summary of presentation, hospital management, interventions, and clinical response using the [DAY_n] timeline.",
        ),
        (
            "Key findings",
            "pertinent documented examination findings, vitals, clinical scales, laboratory results, and imaging.",
        ),
        (
            "Medications at discharge",
            "medications prescribed or continued at discharge with documented doses, routes, and frequencies.",
        ),
        (
            "Follow-up",
            "documented follow-up appointments, repeat investigations, return precautions, or clinician reviews.",
        ),
    ],
    TaskType.case_summary: [
        (
            "Summary",
            "concise overview of the patient presentation (preserving placeholders and age), main diagnoses/problems, and clinical trajectory.",
        ),
        (
            "Key findings",
            "pertinent documented vitals, exam findings, clinical scales, laboratory results, imaging, and treatments.",
        ),
        (
            "Concerns",
            "active clinical risks, abnormal or unresolved findings, complications, or items needing clinical attention evident in the record.",
        ),
    ],
    TaskType.treatment_plan: [
        (
            "Assessment",
            "the working diagnosis, active clinical problems, and current status evident from documented findings in the record.",
        ),
        (
            "Plan",
            "documented therapies, medications (with doses/schedules if stated), procedures, and supportive management steps.",
        ),
        (
            "Monitoring",
            "the parameters already documented in the record that require ongoing follow-up (such as vitals, lab values, glucose/scales, and symptoms).",
        ),
        (
            "Follow-up",
            "scheduled clinician reviews, repeat tests, referrals, or discharge follow-up instructions documented in the record.",
        ),
    ],
}


def _format_headings_with_guidance(task_type: TaskType) -> str:
    return "\n".join(f"- ## {heading}: {guidance}" for heading, guidance in TASK_HEADING_GUIDANCE[task_type])


def build_user_prompt(task_type: TaskType, sanitized_text: str, *, repair: bool = False) -> str:
    """Build outbound LLM user message using ONLY static task instructions + sanitized_text (rules.md P3)."""
    headings_guided = _format_headings_with_guidance(task_type)
    parts = [
        f"Task: {task_type.value.replace('_', ' ')}",
        "Required Markdown headings and what each section should contain (write 'Not documented' only when the record has nothing relevant):",
        headings_guided,
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
    headings_guided = _format_headings_with_guidance(task_type)
    return "\n".join(
        [
            f"Write a structured {TASK_LABELS[task_type]} using only the privacy-safe clinical text below.",
            "Copy all placeholders (such as [PATIENT_A], [DOCTOR_1], [DAY_0]) exactly as written and never guess or invent missing details.",
            "Write 'Not documented' under a heading only when the record has nothing relevant to that section.",
            "",
            "Required headings and what each section should contain:",
            headings_guided,
            "",
            "Clinical text (de-identified):",
            sanitized_text.strip(),
        ]
    )
