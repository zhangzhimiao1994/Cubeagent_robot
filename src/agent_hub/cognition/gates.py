from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from agent_hub.cognition.types import CognitiveEpisode, EpisodeOutcome, EpisodeSignal

_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"bearer\s+[A-Za-z0-9._-]{20,}", re.IGNORECASE),
    re.compile(r"password\s*[:=]\s*\S+", re.IGNORECASE),
)


class LearningGateReason(StrEnum):
    USER_CORRECTION = "user_correction"
    USER_REJECTION = "user_rejection"
    USER_SATISFACTION = "user_satisfaction"
    TASK_OUTCOME = "task_outcome"
    REPEATED_PATTERN = "repeated_pattern"
    DURABLE_PREFERENCE = "durable_preference"
    WORLD_STATE_CHANGE = "world_state_change"
    LOW_VALUE_CHAT = "low_value_chat"
    UNSAFE_CONTENT = "unsafe_content"
    LOW_CONFIDENCE_ASR = "low_confidence_asr"
    MISSING_EVIDENCE = "missing_evidence"


class LearningGateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool
    reason: LearningGateReason
    confidence: float = Field(ge=0, le=1)


def rejects_unsafe_text(text: str) -> bool:
    lowered = text.casefold()
    if "ignore previous instructions" in lowered or "system prompt" in lowered:
        return True
    return any(pattern.search(text) is not None for pattern in _SECRET_PATTERNS)


def learning_gate_decision(episode: CognitiveEpisode) -> LearningGateDecision:
    if episode.privacy_level in {"sensitive", "private"}:
        return LearningGateDecision(accepted=False, reason=LearningGateReason.UNSAFE_CONTENT, confidence=1.0)
    if (
        rejects_unsafe_text(episode.summary)
        or rejects_unsafe_text(episode.feedback)
        or any(
            rejects_unsafe_text(value)
            for evidence in episode.evidence_refs
            for value in (evidence.kind, evidence.ref_id, evidence.summary)
        )
    ):
        return LearningGateDecision(accepted=False, reason=LearningGateReason.UNSAFE_CONTENT, confidence=1.0)
    if EpisodeSignal.SPEECH_RECOGNITION_UNCERTAIN in episode.signals and len(episode.signals) == 1:
        return LearningGateDecision(accepted=False, reason=LearningGateReason.LOW_CONFIDENCE_ASR, confidence=0.85)
    if (
        EpisodeSignal.USER_CORRECTED in episode.signals
        or EpisodeSignal.USER_REJECTED in episode.signals
        or EpisodeSignal.USER_SATISFIED in episode.signals
        or episode.outcome in {EpisodeOutcome.SUCCESS, EpisodeOutcome.FAILURE}
        or EpisodeSignal.REPEATED_PATTERN in episode.signals
        or EpisodeSignal.USER_REPEATED_QUESTION in episode.signals
    ) and not episode.evidence_refs:
        return LearningGateDecision(accepted=False, reason=LearningGateReason.MISSING_EVIDENCE, confidence=1.0)
    if EpisodeSignal.USER_CORRECTED in episode.signals:
        return LearningGateDecision(accepted=True, reason=LearningGateReason.USER_CORRECTION, confidence=0.9)
    if EpisodeSignal.USER_REJECTED in episode.signals:
        return LearningGateDecision(accepted=True, reason=LearningGateReason.USER_REJECTION, confidence=0.85)
    if EpisodeSignal.USER_SATISFIED in episode.signals:
        return LearningGateDecision(accepted=True, reason=LearningGateReason.USER_SATISFACTION, confidence=0.75)
    if episode.outcome in {EpisodeOutcome.SUCCESS, EpisodeOutcome.FAILURE}:
        return LearningGateDecision(accepted=True, reason=LearningGateReason.TASK_OUTCOME, confidence=0.8)
    if EpisodeSignal.REPEATED_PATTERN in episode.signals or EpisodeSignal.USER_REPEATED_QUESTION in episode.signals:
        return LearningGateDecision(accepted=True, reason=LearningGateReason.REPEATED_PATTERN, confidence=0.7)
    return LearningGateDecision(accepted=False, reason=LearningGateReason.LOW_VALUE_CHAT, confidence=0.7)
