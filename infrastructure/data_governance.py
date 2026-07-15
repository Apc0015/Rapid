"""PII detection and redaction used before organization content is indexed."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class GovernanceResult:
    text: str
    findings: dict[str, int]

    @property
    def contains_pii(self) -> bool:
        return any(self.findings.values())


_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])", re.IGNORECASE)),
    ("ssn", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")),
    ("phone", re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)")),
)
_CARD_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")


def _luhn(value: str) -> bool:
    digits = [int(char) for char in value if char.isdigit()]
    if not 13 <= len(digits) <= 19 or len(set(digits)) == 1:
        return False
    total = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def scan_and_redact(text: str, *, redact: bool = True) -> GovernanceResult:
    output = text
    findings: dict[str, int] = {name: 0 for name, _ in _PATTERNS}
    findings["payment_card"] = 0
    for name, pattern in _PATTERNS:
        matches = list(pattern.finditer(output))
        findings[name] += len(matches)
        if redact and matches:
            output = pattern.sub(f"[{name.upper()}_REDACTED]", output)
    card_matches = [match for match in _CARD_CANDIDATE.finditer(output) if _luhn(match.group(0))]
    findings["payment_card"] = len(card_matches)
    if redact:
        for match in reversed(card_matches):
            output = f"{output[:match.start()]}[PAYMENT_CARD_REDACTED]{output[match.end():]}"
    return GovernanceResult(text=output, findings={key: value for key, value in findings.items() if value})
