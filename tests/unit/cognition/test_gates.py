from datetime import UTC, datetime
from uuid import uuid4

import pytest

from agent_hub.cognition.gates import LearningGateReason, learning_gate_decision
from agent_hub.cognition.types import (
    CognitiveEpisode,
    CognitiveSource,
    EpisodeOutcome,
    EpisodeSignal,
    EvidenceRef,
)


def episode(
    summary: str,
    signals: tuple[EpisodeSignal, ...],
    outcome: EpisodeOutcome = EpisodeOutcome.NEUTRAL,
    *,
    evidence_refs: tuple[EvidenceRef, ...] | None = None,
    privacy_level: str = "normal",
) -> CognitiveEpisode:
    return CognitiveEpisode(
        tenant_id=uuid4(),
        user_id=uuid4(),
        source=CognitiveSource.VOICE,
        conversation_id="conv-gates",
        started_at=datetime(2026, 9, 10, 9, 0, tzinfo=UTC),
        summary=summary,
        signals=signals,
        outcome=outcome,
        evidence_refs=(
            (EvidenceRef(kind="conversation", ref_id="conv-gates", summary="gate test"),)
            if evidence_refs is None
            else evidence_refs
        ),
        privacy_level=privacy_level,
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


@pytest.mark.parametrize("privacy_level", ["sensitive", "private"])
def test_learning_gate_rejects_private_episodes(privacy_level: str) -> None:
    decision = learning_gate_decision(
        episode(
            "User corrected the assistant's device setup assumption.",
            (EpisodeSignal.USER_CORRECTED,),
            privacy_level=privacy_level,
        )
    )

    assert decision.accepted is False
    assert decision.reason is LearningGateReason.UNSAFE_CONTENT


def test_learning_gate_rejects_unsafe_evidence_summary() -> None:
    decision = learning_gate_decision(
        episode(
            "User corrected the assistant's device setup assumption.",
            (EpisodeSignal.USER_CORRECTED,),
            evidence_refs=(
                EvidenceRef(
                    kind="conversation",
                    ref_id="conv-gates",
                    summary="credential sk-12345678901234567890",
                ),
            ),
        )
    )

    assert decision.accepted is False
    assert decision.reason is LearningGateReason.UNSAFE_CONTENT


def test_learning_gate_rejects_user_correction_without_evidence() -> None:
    decision = learning_gate_decision(
        episode(
            "User corrected the assistant's device setup assumption.",
            (EpisodeSignal.USER_CORRECTED,),
            evidence_refs=(),
        )
    )

    assert decision.accepted is False
    assert decision.reason is LearningGateReason.MISSING_EVIDENCE


def test_learning_gate_accepts_correction_with_mixed_asr_signal_and_evidence() -> None:
    decision = learning_gate_decision(
        episode(
            "User corrected an uncertain transcription.",
            (EpisodeSignal.SPEECH_RECOGNITION_UNCERTAIN, EpisodeSignal.USER_CORRECTED),
        )
    )

    assert decision.accepted is True
    assert decision.reason is LearningGateReason.USER_CORRECTION
