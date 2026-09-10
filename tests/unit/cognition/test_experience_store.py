from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from agent_hub.cognition.experience_store import ExperienceStore
from agent_hub.cognition.repository import InMemoryCognitionRepository
from agent_hub.cognition.types import (
    CognitiveEpisode,
    CognitiveSource,
    EpisodeOutcome,
    EpisodeSignal,
    EvidenceRef,
    ExperienceKind,
    ExperienceRecord,
)


def _repository() -> tuple[UUID, UUID, InMemoryCognitionRepository]:
    tenant_id = uuid4()
    user_id = uuid4()
    return tenant_id, user_id, InMemoryCognitionRepository(tenant_id=tenant_id, user_id=user_id)


def _existing_experience(tenant_id: UUID, user_id: UUID, **overrides: object) -> ExperienceRecord:
    return ExperienceRecord(
        tenant_id=tenant_id,
        user_id=user_id,
        kind=ExperienceKind.STRATEGY,
        statement="Use concise spoken deployment replies.",
        applicability="voice deployment debugging",
        evidence_refs=(EvidenceRef(kind="conversation", ref_id="conv-1", summary="initial evidence"),),
        **overrides,
    )


@pytest.mark.asyncio
async def test_record_episode_rejects_low_value_chat() -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    store = ExperienceStore(InMemoryCognitionRepository(tenant_id=tenant_id, user_id=user_id))
    episode = CognitiveEpisode(
        tenant_id=tenant_id,
        user_id=user_id,
        source=CognitiveSource.WEB,
        started_at=datetime(2026, 9, 10, 10, 0, tzinfo=UTC),
        summary="User said hello once.",
        evidence_refs=(EvidenceRef(kind="conversation", ref_id="conv-low", summary="one greeting"),),
    )

    result = await store.record_episode(episode)

    assert result.episode_stored is True
    assert result.experience_created is False
    assert result.rejection_reason == "low_value_chat"


@pytest.mark.asyncio
async def test_record_episode_creates_candidate_experience_for_correction() -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    store = ExperienceStore(InMemoryCognitionRepository(tenant_id=tenant_id, user_id=user_id))
    episode = CognitiveEpisode(
        tenant_id=tenant_id,
        user_id=user_id,
        source=CognitiveSource.VOICE,
        conversation_id="conv-correction",
        started_at=datetime(2026, 9, 10, 10, 5, tzinfo=UTC),
        summary="User corrected the assistant for giving long spoken deployment instructions.",
        signals=(EpisodeSignal.USER_CORRECTED,),
        evidence_refs=(EvidenceRef(kind="conversation", ref_id="conv-correction", summary="user correction"),),
    )

    result = await store.record_episode(episode)

    assert result.experience_created is True
    assert result.experience is not None
    assert result.experience.kind.value == "failure_pattern"
    assert result.experience.status.value == "candidate"


@pytest.mark.asyncio
async def test_record_episode_persists_reflection_when_experience_is_created() -> None:
    tenant_id, user_id, repository = _repository()
    store = ExperienceStore(repository)
    evidence = EvidenceRef(kind="conversation", ref_id="conv-correction", summary="user correction")
    episode = CognitiveEpisode(
        tenant_id=tenant_id,
        user_id=user_id,
        source=CognitiveSource.VOICE,
        conversation_id="conv-correction",
        started_at=datetime(2026, 9, 10, 10, 5, tzinfo=UTC),
        summary="User corrected the assistant for giving long spoken deployment instructions.",
        signals=(EpisodeSignal.USER_CORRECTED,),
        evidence_refs=(evidence,),
    )

    result = await store.record_episode(episode)
    reflections = await repository.list("reflection")

    assert result.experience_created is True
    assert result.experience is not None
    assert len(reflections) == 1
    reflection = reflections[0]
    assert reflection["record_type"] == "reflection"
    assert reflection["episode_id"] == str(episode.id)
    assert reflection["reflection_type"] == "negative"
    assert reflection["trigger"] == "user_corrected"
    assert reflection["what_happened"] == episode.summary
    assert reflection["candidate_experience_ids"] == [str(result.experience.id)]
    assert reflection["confidence"] == 0.72
    assert reflection["requires_approval"] is False
    assert reflection["evidence_refs"] == [evidence.model_dump(mode="json")]


@pytest.mark.asyncio
async def test_record_episode_does_not_persist_reflection_for_rejected_episode() -> None:
    tenant_id, user_id, repository = _repository()
    store = ExperienceStore(repository)
    episode = CognitiveEpisode(
        tenant_id=tenant_id,
        user_id=user_id,
        source=CognitiveSource.WEB,
        started_at=datetime(2026, 9, 10, 10, 0, tzinfo=UTC),
        summary="User said hello once.",
        evidence_refs=(EvidenceRef(kind="conversation", ref_id="conv-low", summary="one greeting"),),
    )

    result = await store.record_episode(episode)

    assert result.experience_created is False
    assert await repository.list("reflection") == ()


@pytest.mark.asyncio
async def test_record_episode_always_persists_episode_before_gate_result() -> None:
    tenant_id, user_id, repository = _repository()
    store = ExperienceStore(repository)
    episode = CognitiveEpisode(
        tenant_id=tenant_id,
        user_id=user_id,
        source=CognitiveSource.WEB,
        started_at=datetime(2026, 9, 10, 10, 0, tzinfo=UTC),
        summary="User said hello once.",
        evidence_refs=(EvidenceRef(kind="conversation", ref_id="conv-low", summary="one greeting"),),
    )

    result = await store.record_episode(episode)
    stored = await repository.get("episode", str(episode.id))

    assert result.experience_created is False
    assert stored is not None
    assert stored["record_type"] == "episode"
    assert stored["summary"] == "User said hello once."
    assert stored["tenant_id"] == str(tenant_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("signals", "outcome", "expected_kind"),
    [
        ((EpisodeSignal.USER_INTERRUPTED, EpisodeSignal.USER_CORRECTED), EpisodeOutcome.NEUTRAL, "voice_interaction"),
        (
            (EpisodeSignal.SPEECH_RECOGNITION_UNCERTAIN, EpisodeSignal.USER_CORRECTED),
            EpisodeOutcome.NEUTRAL,
            "voice_interaction",
        ),
        ((EpisodeSignal.USER_REJECTED,), EpisodeOutcome.NEUTRAL, "failure_pattern"),
        ((EpisodeSignal.USER_SATISFIED,), EpisodeOutcome.NEUTRAL, "success_pattern"),
        ((EpisodeSignal.TASK_SUCCEEDED,), EpisodeOutcome.SUCCESS, "success_pattern"),
        ((), EpisodeOutcome.SUCCESS, "strategy"),
        ((EpisodeSignal.REPEATED_PATTERN,), EpisodeOutcome.NEUTRAL, "strategy"),
    ],
)
async def test_record_episode_maps_accepted_patterns_to_experience_kind(
    signals: tuple[EpisodeSignal, ...],
    outcome: EpisodeOutcome,
    expected_kind: str,
) -> None:
    tenant_id, user_id, repository = _repository()
    store = ExperienceStore(repository)
    episode = CognitiveEpisode(
        tenant_id=tenant_id,
        user_id=user_id,
        source=CognitiveSource.VOICE,
        conversation_id="conv-pattern",
        started_at=datetime(2026, 9, 10, 10, 5, tzinfo=UTC),
        summary="User gave durable feedback about spoken deployment debugging.",
        signals=signals,
        outcome=outcome,
        evidence_refs=(EvidenceRef(kind="conversation", ref_id="conv-pattern", summary="pattern evidence"),),
    )

    result = await store.record_episode(episode)

    assert result.experience_created is True
    assert result.experience is not None
    assert result.experience.kind.value == expected_kind
    assert await repository.get("experience", str(result.experience.id)) is not None


@pytest.mark.asyncio
async def test_record_outcome_success_updates_usage_verification_evidence_and_confidence() -> None:
    tenant_id, user_id, repository = _repository()
    store = ExperienceStore(repository)
    experience = _existing_experience(tenant_id, user_id, confidence=0.98)
    await repository.upsert("experience", str(experience.id), experience.model_dump(mode="json"))
    evidence = EvidenceRef(kind="conversation", ref_id="conv-success", summary="successful reuse")

    updated = await store.record_outcome(experience.id, succeeded=True, evidence=evidence)
    persisted = await repository.get("experience", str(experience.id))

    assert updated.usage_count == 1
    assert updated.success_count == 1
    assert updated.failure_count == 0
    assert updated.last_used_at is not None
    assert updated.last_verified_at == updated.last_used_at
    assert updated.evidence_refs[-1] == evidence
    assert updated.contradictions == ()
    assert updated.version == 2
    assert updated.confidence == 1.0
    assert persisted is not None
    assert persisted["success_count"] == 1


@pytest.mark.asyncio
async def test_record_outcome_failure_updates_usage_contradictions_and_confidence() -> None:
    tenant_id, user_id, repository = _repository()
    store = ExperienceStore(repository)
    experience = _existing_experience(tenant_id, user_id, confidence=0.02)
    await repository.upsert("experience", str(experience.id), experience.model_dump(mode="json"))
    evidence = EvidenceRef(kind="conversation", ref_id="conv-failure", summary="failed reuse")

    updated = await store.record_outcome(experience.id, succeeded=False, evidence=evidence)

    assert updated.usage_count == 1
    assert updated.success_count == 0
    assert updated.failure_count == 1
    assert updated.last_used_at is not None
    assert updated.last_verified_at is None
    assert updated.evidence_refs == experience.evidence_refs
    assert updated.contradictions == (evidence,)
    assert updated.version == 2
    assert updated.confidence == 0.0


@pytest.mark.asyncio
async def test_record_outcome_missing_experience_raises_lookup_error() -> None:
    _, _, repository = _repository()
    store = ExperienceStore(repository)

    with pytest.raises(LookupError, match="experience"):
        await store.record_outcome(
            uuid4(),
            succeeded=True,
            evidence=EvidenceRef(kind="conversation", ref_id="conv-missing", summary="missing"),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(("reason", "expected_status"), [("stale", "stale"), ("wrong", "rejected"), ("unsafe", "rejected")])
async def test_retire_experience_sets_status_for_valid_reasons(reason: str, expected_status: str) -> None:
    tenant_id, user_id, repository = _repository()
    store = ExperienceStore(repository)
    experience = _existing_experience(tenant_id, user_id)
    await repository.upsert("experience", str(experience.id), experience.model_dump(mode="json"))

    updated = await store.retire_experience(experience.id, reason=reason)

    assert updated.status.value == expected_status
    assert updated.version == 2
    assert updated.updated_at > experience.updated_at
    assert (await repository.get("experience", str(experience.id)))["status"] == expected_status


@pytest.mark.asyncio
async def test_retire_experience_rejects_invalid_reason() -> None:
    tenant_id, user_id, repository = _repository()
    store = ExperienceStore(repository)
    experience = _existing_experience(tenant_id, user_id)
    await repository.upsert("experience", str(experience.id), experience.model_dump(mode="json"))

    with pytest.raises(ValueError, match="retirement reason"):
        await store.retire_experience(experience.id, reason="duplicate")


@pytest.mark.asyncio
async def test_retire_experience_missing_experience_raises_lookup_error() -> None:
    _, _, repository = _repository()
    store = ExperienceStore(repository)

    with pytest.raises(LookupError, match="experience"):
        await store.retire_experience(uuid4(), reason="stale")
