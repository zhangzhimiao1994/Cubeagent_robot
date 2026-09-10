from __future__ import annotations

import re

from agent_hub.cognition.types import (
    BeliefRecord,
    BeliefStatus,
    CognitiveRecordStatus,
    ExperienceKind,
    ExperienceRecord,
)
from agent_hub.evolution import EvolutionRunRequest

_HERMES_LESSON_MAX_LENGTH = 4000
_TEXT_FIELD_MAX_LENGTH = 900
_MEMORY_TEXT_MAX_LENGTH = 1000
_ELIGIBLE_EXPERIENCE_KINDS = {
    ExperienceKind.STRATEGY,
    ExperienceKind.TOOL_PATTERN,
    ExperienceKind.SUCCESS_PATTERN,
}
_SENSITIVE_SCOPES = {"sensitive", "private", "security", "secret", "password", "token"}
_SECRET_LIKE_TEXT = re.compile(
    r"(?i)\b(bearer\s+)[a-z0-9._:-]+|"
    r"\b(password|secret|token)\s*=\s*[^\s,;.]+|"
    r"\bsk-[a-z0-9_-]+\b"
)


def hermes_feedback_from_experience(experience: ExperienceRecord) -> dict[str, object]:
    lesson = _bounded_text(
        (
            f"{_public_text(experience.statement)} Recommended action: "
            f"{_public_text(experience.recommended_action)}"
        ),
        max_length=_HERMES_LESSON_MAX_LENGTH,
    )
    return {
        "category": "conversation",
        "outcome": "success" if experience.success_count >= experience.failure_count else "failure",
        "lesson": lesson,
        "tags": [experience.kind.value, "cognition"],
        "weight": max(1, min(10, int(round(experience.confidence * 10)))),  # noqa: RUF046
    }


def evolution_request_from_experiences(
    experiences: tuple[ExperienceRecord, ...],
) -> EvolutionRunRequest | None:
    eligible = tuple(experience for experience in experiences if _is_evolution_candidate(experience))
    if not eligible:
        return None

    objective_items = []
    for experience in eligible[:5]:
        statement = _public_text(experience.statement, max_length=_TEXT_FIELD_MAX_LENGTH)
        action = _public_text(experience.recommended_action, max_length=_TEXT_FIELD_MAX_LENGTH)
        if action:
            objective_items.append(
                f"- {experience.kind.value}: {statement} Recommended action: {action}"
            )
        else:
            objective_items.append(f"- {experience.kind.value}: {statement}")
    objective = _bounded_text(
        "Improve cognitive skill behavior from repeated successful experiences:\n"
        + "\n".join(objective_items),
        max_length=6000,
    )

    return EvolutionRunRequest(
        kind="skill_optimization",
        title="Cognitive skill improvement",
        objective=objective,
        approval_policy="ask",
        iteration_policy="score_gated",
        memory_policy="summarize_between_rounds",
        max_rounds=3,
        min_delta=2.0,
        rubric=[
            "Preserve behavior proven by repeated active cognitive experiences.",
            "Reject changes that reduce safety, privacy, or deterministic adapter behavior.",
            "Score higher only when the skill improvement is specific, bounded, and testable.",
        ],
    )


def memory_candidate_from_belief(belief: BeliefRecord) -> dict[str, object] | None:
    if belief.confidence < 0.75:
        return None
    if belief.status is not BeliefStatus.ACTIVE:
        return None
    if belief.contradictions:
        return None
    if _is_sensitive_scope(belief.scope):
        return None

    text = _public_text(
        f"{belief.subject} {belief.predicate} {belief.object}",
        max_length=_MEMORY_TEXT_MAX_LENGTH,
    )
    if not text or "[redacted]" in text:
        return None
    return {
        "layer": "episodic",
        "category": "fact",
        "text": text,
        "confidence": belief.confidence,
        "metadata": {"source": "cognition_belief"},
    }


def _is_evolution_candidate(experience: ExperienceRecord) -> bool:
    return (
        experience.status is CognitiveRecordStatus.ACTIVE
        and experience.usage_count >= 3
        and experience.success_count >= 3
        and experience.failure_count == 0
        and experience.confidence >= 0.8
        and experience.kind in _ELIGIBLE_EXPERIENCE_KINDS
    )


def _is_sensitive_scope(scope: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", scope.casefold())
    return any(part in _SENSITIVE_SCOPES for part in normalized.split("_") if part)


def _public_text(value: str, *, max_length: int = _TEXT_FIELD_MAX_LENGTH) -> str:
    redacted = _SECRET_LIKE_TEXT.sub(_redaction, value)
    return _bounded_text(" ".join(redacted.split()), max_length=max_length)


def _bounded_text(value: str, *, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3].rstrip() + "..."


def _redaction(match: re.Match[str]) -> str:
    prefix = match.group(1)
    if prefix:
        return f"{prefix}[redacted]"
    return "[redacted]"


__all__ = [
    "evolution_request_from_experiences",
    "hermes_feedback_from_experience",
    "memory_candidate_from_belief",
]
