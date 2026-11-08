"""Deterministic promotional scoring for PromoIQ."""

import re
from typing import Dict


def _has(text: str, patterns: list[str]) -> bool:
    """Check whether any meaningful pattern occurs in the text."""
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


HOOK_STAKES = [
    r"\b(hang|hanged|execute|execution|kill|killed|die|dead|murder|poison|arrest|burn|destroy|betray|betrayed|expose|imprison|blackmail)\b",
]

HOOK_URGENCY = [
    r"\b(unless|or else|at dawn|tonight|tomorrow|before it's too late|last chance)\b",
    r"\byou have \d+\s+(seconds|minutes|hours)\b",
]

HOOK_CONFRONTATION = [
    r"\bhow dare\b",
    r"\byou\s+(lied|betrayed|poisoned|killed|stole|planted|framed|abandoned)\b",
    r"\bi know what you did\b",
    r"\btell me the truth\b",
    r"\bthis is your fault\b",

    r"\bthis is where you (live|belong)\b",
    r"\byou look like an? (servant|beggar|failure|fool)\b",
    r"\bfitting home for\b",
    r"\byou threw (everything|it all) away\b",
    r"\bworthless\b",
    r"\bpenniless\b",

    r"\bturn around\b",
    r"\bnot anymore\b",
    r"\bbecause he is marrying me\b",
    r"\bholding (her|his|their) hand\b",
]

HOOK_MYSTERY = [
    r"\bwho are you\b",
    r"\bwhat have you done\b",
    r"\bwhat happened\b",
    r"\bwhat do you mean\b",
    r"\bwhy (are|is|did|do) you\b",
    r"\bwhere is (he|she|it|the)\b",
    r"\bwhat is (he|she|they) hiding\b",
    r"\bsecret identity\b",
]

CLIFF_THREAT = [
    r"\b(will|shall|must|going to|about to)\s+(be\s+)?(hang|hanged|executed|killed|die|drown|burn|arrested|imprisoned|exposed|revealed|destroyed|poisoned)\b",
]

CLIFF_CONDITIONAL = [
    r"\bunless\b",
    r"\bor else\b",
    r"\bat dawn\b",
    r"\bbefore it's too late\b",
    r"\btonight\b",
    r"\byou have \d+\s+(seconds|minutes|hours)\b",
]

CLIFF_OPEN_LOOP = [
    r"\bwho are you\b",
    r"\bwhat happened\b",
    r"\bwhere is (he|she|it|the)\b",
    r"\bwhat is (he|she|they) hiding\b",
    r"\bwill (he|she|they)\b",
    r"\bwhat will happen\b",
]

CLIFF_SUSPENSE = [
    r"\bsecret\b",
    r"\bidentity\b",
    r"\bfootsteps\b",
    r"\bdoor opens\b",
    r"\bjust then\b",
    r"\babout to\b",
    r"\b(you|he|she|they) don't know\b",
    r"\bthe truth is\b",
    r"\bwait until\b",
    r"\bthere's someone\b",
    r"\bbehind you\b",
    r"\bthe real (killer|heir|owner|identity)\b",
]

CLIFF_WARNING = [
    r"\b(turn around|look for yourself|don't move|do not move)\b",
    r"\b(run|stay away|stop|listen|be careful|watch out)\b",
    r"\b(warning|beware|i'm warning you|i am warning you)\b",
    r"\b(you must leave|leave now|get out|go back)\b",
]

RESOLUTION = [
    r"\b(you are|you're|he is|she is|we are|i am)\s+(safe|free|home|forgiven)\b",
    r"\b(it's|it is|that is|this is)\s+(over|finished|done)\b",
    r"\bno one is in danger\b",
    r"\bwe made it\b",
    r"\bcase closed\b",
    r"\bthe danger is gone\b",
    r"\beverything is fine\b",
]


def _hook_score(text: str) -> float:
    score = 25.0

    if _has(text, HOOK_STAKES):
        score += 28

    if _has(text, HOOK_URGENCY):
        score += 20

    if _has(text, HOOK_CONFRONTATION):
        score += 17

    if _has(text, HOOK_MYSTERY):
        score += 15

    if "!" in text:
        score += 5

    return round(_clamp(score), 1)


def _cliffhanger_score(text: str) -> float:
    score = 25.0

    if _has(text, CLIFF_THREAT):
        score += 40

    if _has(text, CLIFF_CONDITIONAL):
        score += 20

    if _has(text, CLIFF_OPEN_LOOP):
        score += 15

    if _has(text, CLIFF_SUSPENSE):
        score += 8

    if _has(text, CLIFF_WARNING):
        score += 18

    # A resolved ending should not be rewarded merely because it contains
    # generic words such as "wait", "but" or "didn't".
    if _has(text, RESOLUTION):
        score -= 45

    if text.rstrip().endswith("..."):
        score += 5

    return round(_clamp(score), 1)


def _standalone_score(text: str) -> float:
    words = text.split()
    word_count = len(words)

    score = 35.0

    if 20 <= word_count <= 110:
        score += 20
    elif word_count < 8:
        score -= 12
    elif word_count > 160:
        score -= 10

    # Reward scenes in which viewers can identify the speakers.
    speakers = set(
        re.findall(r"\b([A-Z][A-Z .'-]{1,25}):", text)
    )
    score += min(len(speakers), 3) * 10

    relationships = [
        "wife", "husband", "mother", "father",
        "daughter", "son", "sister", "brother"
    ]

    relationship_count = sum(
        1 for term in relationships
        if re.search(r"\b" + term + r"\b", text, re.IGNORECASE)
    )

    score += min(relationship_count, 2) * 5

    return round(_clamp(score), 1)


def _duration_score(duration: float) -> float:
    """Prefer approximately 40-second clips within the 20–60s range."""

    if 20 <= duration <= 60:
        return round(100 - abs(duration - 40) * 1.5, 1)

    if duration < 20:
        distance = 20 - duration
    else:
        distance = duration - 60

    return round(_clamp(70 - distance * 3), 1)


def _evidence_completeness(text: str, hook_text: str, cliff_text: str) -> float:
    """Reward source-grounded story evidence, not generated descriptions."""
    score = 35.0
    words = len(text.split())
    if words >= 35:
        score += 20
    elif words < 12:
        score -= 15

    if re.search(r"\\b[A-Z][A-Z .'-]{1,25}:\\s", text):
        score += 15
    if re.search(r"\\b(because|but|unless|when|then|however)\\b", text, re.I):
        score += 15
    if hook_text.strip() and cliff_text.strip() and hook_text.strip() != cliff_text.strip():
        score += 15
    return round(_clamp(score), 1)


def score_candidate(
    text: str,
    duration: float,
    start_text: str = "",
    end_text: str = "",
) -> Dict:
    """Score a candidate using transparent, deterministic editorial signals.

    Weighting prioritizes the opening and ending while preserving enough
    weight for standalone comprehension. No score is a substitute for viewing
    the actual footage.
    """
    hook_text = start_text or text[:220]
    cliff_text = end_text or text[-220:]

    hook = _hook_score(hook_text)
    cliff = _cliffhanger_score(cliff_text)
    standalone = _standalone_score(text)
    duration_score = _duration_score(duration)
    evidence = _evidence_completeness(text, hook_text, cliff_text)

    total = (
        0.30 * hook
        + 0.30 * cliff
        + 0.25 * standalone
        + 0.10 * duration_score
        + 0.05 * evidence
    )

    return {
        "hook_score": hook,
        "cliffhanger_score": cliff,
        "standalone_score": standalone,
        "duration_score": duration_score,
        "evidence_completeness_score": evidence,
        "total_score": round(total, 1),
    }
