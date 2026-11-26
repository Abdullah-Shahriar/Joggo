from dataclasses import dataclass
import re

from app.services.llm.prompts import AI_DISCLAIMER

BRACKETED_TOKEN_RE = re.compile(
    r"\[((?:PATIENT|DOCTOR|PERSON|PHONE|EMAIL|ID|MRN|LOCATION|FACILITY|URL|IP|OTHER|DAY)_[A-Z0-9?-]+)\]",
    re.IGNORECASE,
)
BARE_TOKEN_RE = re.compile(
    r"(?<!\[)\b((?:PATIENT|DOCTOR|PERSON|PHONE|EMAIL|ID|MRN|LOCATION|FACILITY|URL|IP|OTHER|DAY)_[A-Z0-9?-]+)\b(?!\])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RehydrateResult:
    text: str
    rehydrated: bool
    vault_expired: bool
    warnings: list[dict[str, str]]


def _append_disclaimer(text: str) -> str:
    stripped = text.strip()
    if AI_DISCLAIMER in stripped:
        return stripped
    return f"{stripped}\n\n{AI_DISCLAIMER}"


def rehydrate_text(
    tokenized_text: str,
    mapping: dict[str, str] | None,
) -> RehydrateResult:
    """Restore real details locally in memory (never persisted, architecture.md §18)."""
    if mapping is None:
        return RehydrateResult(
            text=_append_disclaimer(tokenized_text),
            rehydrated=False,
            vault_expired=True,
            warnings=[],
        )

    # Case-insensitive lookup for both "[TYPE_ID]" and bare "TYPE_ID"
    lookup: dict[str, str] = {}
    for token, real_val in mapping.items():
        inner = token.strip("[]").upper()
        lookup[inner] = real_val

    warnings: list[dict[str, str]] = []
    warned_tokens: set[str] = set()

    def _replace_bracketed(m: re.Match[str]) -> str:
        inner = m.group(1).upper()
        if inner in lookup:
            return lookup[inner]
        raw_tok = m.group(0)
        if raw_tok not in warned_tokens:
            warned_tokens.add(raw_tok)
            warnings.append({"code": "UNKNOWN_TOKEN", "token": raw_tok})
        return raw_tok

    def _replace_bare(m: re.Match[str]) -> str:
        inner = m.group(1).upper()
        if inner in lookup:
            return lookup[inner]
        raw_tok = m.group(0)
        if raw_tok not in warned_tokens:
            warned_tokens.add(raw_tok)
            warnings.append({"code": "UNKNOWN_TOKEN", "token": raw_tok})
        return raw_tok

    step1 = BRACKETED_TOKEN_RE.sub(_replace_bracketed, tokenized_text)
    step2 = BARE_TOKEN_RE.sub(_replace_bare, step1)

    return RehydrateResult(
        text=_append_disclaimer(step2),
        rehydrated=True,
        vault_expired=False,
        warnings=warnings,
    )
