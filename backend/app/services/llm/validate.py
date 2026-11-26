import re

from app.models.document import TaskType
from app.services.llm.prompts import TASK_HEADINGS

MAX_LLM_OUTPUT_CHARS = 20_000

REFUSAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bi\s+cannot\b", re.IGNORECASE),
    re.compile(r"\bi\s+can't\s+(?:assist|help|fulfill|provide|generate)\b", re.IGNORECASE),
    re.compile(r"\bi\s+am\s+sorry,\s+but\s+i\s+cannot\b", re.IGNORECASE),
    re.compile(r"\bas\s+an\s+ai\s+(?:language\s+)?model\b", re.IGNORECASE),
)


def validate_llm_output(text: str, task_type: TaskType) -> tuple[bool, str | None]:
    """Validate LLM Markdown output per architecture.md §16."""
    if not isinstance(text, str):
        return False, "Response is not text"
    stripped = text.strip()
    if not stripped:
        return False, "Empty response"
    if len(stripped) > MAX_LLM_OUTPUT_CHARS:
        return False, "Response exceeds maximum allowed length"
    try:
        stripped.encode("utf-8")
    except UnicodeEncodeError:
        return False, "Invalid UTF-8 content"

    for pat in REFUSAL_PATTERNS:
        if pat.search(stripped):
            return False, "Response contains refusal placeholder"

    required = TASK_HEADINGS[task_type]
    for heading in required:
        heading_re = re.compile(rf"(?im)^\s*##\s+{re.escape(heading)}\s*$")
        if not heading_re.search(stripped):
            return False, f"Missing required heading: ## {heading}"

    return True, None
