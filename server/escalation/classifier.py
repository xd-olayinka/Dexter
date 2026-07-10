import re
from models import EscalationLevel


CLOUD_FORCE_PATTERNS = re.compile(
    r"use\s+claude|use\s+gpt|use\s+opus|use\s+sonnet|\bescalate\b",
    re.IGNORECASE,
)

CLOUD_LEAN_KEYWORDS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\banalyz[ei]\b", r"\breview\b", r"\baudit\b", r"\bcompar[ei]\b",
        r"\bexplain\s+why\b", r"\brefactor\b", r"\barchitect\b",
        r"\bdesign\s+system\b", r"\bdebug\b", r"\boptimize\b",
    ]
]

CODE_BLOCK_PATTERN = re.compile(r"```[\s\S]{20,}```", re.DOTALL)

FAST_GREETINGS = re.compile(
    r"^(hi|hey|hello|yo|sup|thanks|thank you|ok|okay|cool|bye|good\s*(morning|evening|night)|what'?s?\s+up)\s*[!?.]?$",
    re.IGNORECASE,
)


class TaskClassifier:
    def __init__(self):
        self._override: EscalationLevel | None = None

    def classify(self, message: str, context: list[dict] | None = None) -> EscalationLevel:
        if self._override is not None:
            level = self._override
            self._override = None
            return level

        stripped = message.strip()

        if CLOUD_FORCE_PATTERNS.search(stripped):
            return EscalationLevel.CLOUD

        if len(stripped) < 100 and FAST_GREETINGS.match(stripped):
            return EscalationLevel.FAST

        cloud_signals = 0

        if len(stripped) > 2000:
            cloud_signals += 2

        for pattern in CLOUD_LEAN_KEYWORDS:
            if pattern.search(stripped):
                cloud_signals += 1

        if CODE_BLOCK_PATTERN.search(stripped):
            cloud_signals += 1

        if re.search(r"\b(code\s+review|review\s+(this|my)\s+code)\b", stripped, re.IGNORECASE):
            cloud_signals += 1

        if cloud_signals >= 2:
            return EscalationLevel.CLOUD

        if cloud_signals == 0 and len(stripped) < 100:
            return EscalationLevel.FAST

        return EscalationLevel.LOCAL

    def override(self, level: EscalationLevel) -> EscalationLevel:
        self._override = level
        return level
