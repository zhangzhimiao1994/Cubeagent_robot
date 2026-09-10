from datetime import UTC, datetime
from uuid import uuid4

from agent_hub.cognition.gates import LearningGateReason, learning_gate_decision
from agent_hub.cognition.types import (
    CognitiveEpisode,
    CognitiveSource,
    EpisodeOutcome,
    EpisodeSignal,
    EvidenceRef,
)


def episode(summary: str, signals: tuple[EpisodeSignal, ...], outcome: EpisodeOutcome = EpisodeOutcome.NEUTRAL) -> CognitiveEpisode:
    return CognitiveEpisode(
        tenant_id=uuid4(),
        user_id=uuid4(),
        source=CognitiveSource.VOICE,
        conversation_id="conv-gates",
        started_at=datetime(2026, 9, 10, 9, 0, tzinfo=UTC),
        summary=summary,
        signals=signals,
        outcome=outcome,
        evidence_refs=(EvidenceRef(kind="conversation", ref_id="conv-gates", summary="gate test"),),
    )


def test_learning_gate_rejects_ordinary_chat() -> None:
    decision = learning_gate_decision(episode("User chatted about the weather once.", ()))

    assert decision.accepted is False
    assert decision.reason is LearningGateReason.LOW_VALUE_CHAT


def test_learning_gate_accepts_user_correction() -> None:
    decision = learning_gate_decision(
        episode("User corrected the assistant's device setup assumption.", (EpisodeSignal.USER_CORRECTED,))
    )

    assert decision.accepted is True
    assert decision.reason is LearningGateReason.USER_CORRECTION
