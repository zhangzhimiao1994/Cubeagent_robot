from datetime import UTC, datetime
from uuid import uuid4

import pytest

from agent_hub.cognition.types import (
    BeliefRecord,
    CognitiveEpisode,
    CognitiveRecordStatus,
    CognitiveSource,
    EpisodeOutcome,
    EpisodeSignal,
    EvidenceRef,
    ExperienceKind,
    ExperienceRecord,
    ProtectedChangeProposal,
)


def test_experience_requires_evidence_and_bounded_statement() -> None:
    tenant_id = uuid4()
    user_id = uuid4()

    with pytest.raises(ValueError, match="evidence"):
        ExperienceRecord(
            tenant_id=tenant_id,
            user_id=user_id,
            kind=ExperienceKind.VOICE_INTERACTION,
            statement="The user prefers concise deployment debugging replies.",
            applicability="voice replies during technical deployment debugging",
            recommended_action="Give one concrete step first, then ask whether to expand.",
            evidence_refs=(),
        )


def test_episode_accepts_structured_feedback_signal() -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    episode = CognitiveEpisode(
        tenant_id=tenant_id,
        user_id=user_id,
        source=CognitiveSource.VOICE,
        conversation_id="conv-voice-1",
        started_at=datetime(2026, 9, 10, 8, 0, tzinfo=UTC),
        ended_at=datetime(2026, 9, 10, 8, 1, tzinfo=UTC),
        summary="User interrupted a long spoken deployment explanation.",
        signals=(EpisodeSignal.USER_INTERRUPTED,),
        outcome=EpisodeOutcome.NEUTRAL,
        evidence_refs=(EvidenceRef(kind="conversation", ref_id="conv-voice-1", summary="voice turn"),),
    )

    assert episode.source is CognitiveSource.VOICE
    assert episode.signals == (EpisodeSignal.USER_INTERRUPTED,)


def test_belief_record_has_reviewable_version_metadata() -> None:
    record = BeliefRecord(
        tenant_id=uuid4(),
        user_id=uuid4(),
        subject="user",
        predicate="prefers",
        object="concise replies",
        evidence_refs=(EvidenceRef(kind="conversation", ref_id="conv-1", summary="feedback"),),
        version=1,
    )

    assert record.version == 1


def test_protected_change_proposal_has_reviewable_metadata() -> None:
    proposal = ProtectedChangeProposal(
        target="self_model",
        proposed_change="Update capability boundary after repeated evidence.",
        evidence_refs=(EvidenceRef(kind="conversation", ref_id="conv-1", summary="review"),),
        confidence=0.5,
        status=CognitiveRecordStatus.CANDIDATE,
        version=1,
    )

    assert proposal.requires_approval is True
    assert proposal.status is CognitiveRecordStatus.CANDIDATE
    assert proposal.version == 1
