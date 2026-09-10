from datetime import UTC, datetime
from uuid import uuid4

import pytest

from agent_hub.cognition.reflection import ReflectionEngine
from agent_hub.cognition.types import (
    CognitiveEpisode,
    CognitiveSource,
    EpisodeOutcome,
    EpisodeSignal,
    EvidenceRef,
    ExperienceKind,
    ExperienceRecord,
    ReflectionTrigger,
    ReflectionType,
)


def _episode(**overrides: object) -> CognitiveEpisode:
    values = {
        "tenant_id": uuid4(),
        "user_id": uuid4(),
        "source": CognitiveSource.TASK,
        "started_at": datetime(2026, 9, 10, 11, 0, tzinfo=UTC),
        "summary": "The assistant handled a deployment task.",
        "evidence_refs": (EvidenceRef(kind="run", ref_id="run-1", summary="deployment run"),),
    }
    values.update(overrides)
    return CognitiveEpisode(**values)


def test_reflection_creates_counterfactual_for_failure() -> None:
    episode = CognitiveEpisode(
        tenant_id=uuid4(),
        user_id=uuid4(),
        source=CognitiveSource.TASK,
        started_at=datetime(2026, 9, 10, 11, 0, tzinfo=UTC),
        summary="Deployment failed after the assistant skipped a health check.",
        signals=(EpisodeSignal.TASK_FAILED,),
        outcome=EpisodeOutcome.FAILURE,
        evidence_refs=(EvidenceRef(kind="run", ref_id="run-failed", summary="deployment failure"),),
    )

    reflection = ReflectionEngine().reflect(episode)

    assert reflection.reflection_type is ReflectionType.COUNTERFACTUAL
    assert "health check" in reflection.better_next_time.lower()
    assert reflection.requires_approval is False


def test_reflection_copies_episode_and_experience_fields() -> None:
    episode = _episode(summary="User was satisfied after a short deployment update.")
    experience = ExperienceRecord(
        tenant_id=episode.tenant_id,
        user_id=episode.user_id,
        kind=ExperienceKind.SUCCESS_PATTERN,
        statement="Short deployment updates work well.",
        applicability="deployment status updates",
        evidence_refs=episode.evidence_refs,
    )

    reflection = ReflectionEngine().reflect(episode, experience)

    assert reflection.episode_id == episode.id
    assert reflection.what_happened == "User was satisfied after a short deployment update."
    assert reflection.candidate_experience_ids == (experience.id,)
    assert reflection.confidence == 0.72
    assert reflection.requires_approval is False
    assert reflection.evidence_refs == episode.evidence_refs
    assert reflection.candidate_belief_updates == ()
    assert reflection.candidate_skill_updates == ()


@pytest.mark.parametrize(
    ("signals", "outcome", "expected_type", "expected_trigger"),
    [
        ((EpisodeSignal.TASK_FAILED,), EpisodeOutcome.NEUTRAL, ReflectionType.COUNTERFACTUAL, ReflectionTrigger.TASK_FAILED),
        ((EpisodeSignal.USER_CORRECTED,), EpisodeOutcome.NEUTRAL, ReflectionType.NEGATIVE, ReflectionTrigger.USER_CORRECTED),
        ((EpisodeSignal.USER_SATISFIED,), EpisodeOutcome.NEUTRAL, ReflectionType.POSITIVE, ReflectionTrigger.USER_SATISFIED),
        ((EpisodeSignal.TASK_SUCCEEDED,), EpisodeOutcome.NEUTRAL, ReflectionType.POSITIVE, ReflectionTrigger.TASK_SUCCEEDED),
        ((EpisodeSignal.REPEATED_PATTERN,), EpisodeOutcome.NEUTRAL, ReflectionType.CAUSAL, ReflectionTrigger.REPEATED_PATTERN),
        (
            (EpisodeSignal.USER_REPEATED_QUESTION,),
            EpisodeOutcome.NEUTRAL,
            ReflectionType.CAUSAL,
            ReflectionTrigger.REPEATED_PATTERN,
        ),
        ((), EpisodeOutcome.SUCCESS, ReflectionType.POSITIVE, ReflectionTrigger.TASK_SUCCEEDED),
        ((), EpisodeOutcome.FAILURE, ReflectionType.COUNTERFACTUAL, ReflectionTrigger.TASK_FAILED),
        ((), EpisodeOutcome.UNCERTAIN, ReflectionType.MIXED, ReflectionTrigger.AGENT_UNCERTAIN),
    ],
)
def test_reflection_maps_signal_and_outcome_to_type_and_trigger(
    signals: tuple[EpisodeSignal, ...],
    outcome: EpisodeOutcome,
    expected_type: ReflectionType,
    expected_trigger: ReflectionTrigger,
) -> None:
    reflection = ReflectionEngine().reflect(_episode(signals=signals, outcome=outcome))

    assert reflection.reflection_type is expected_type
    assert reflection.trigger is expected_trigger


def test_reflection_prefers_failure_mapping_over_success_signal() -> None:
    episode = _episode(signals=(EpisodeSignal.USER_SATISFIED,), outcome=EpisodeOutcome.FAILURE)

    reflection = ReflectionEngine().reflect(episode)

    assert reflection.reflection_type is ReflectionType.COUNTERFACTUAL
    assert reflection.trigger is ReflectionTrigger.TASK_FAILED


def test_reflection_uses_voice_specific_next_action_for_long_summary() -> None:
    episode = _episode(
        source=CognitiveSource.VOICE,
        summary="The spoken answer was too long for the user.",
        signals=(EpisodeSignal.USER_CORRECTED,),
    )

    reflection = ReflectionEngine().reflect(episode)

    assert reflection.better_next_time == "Use a shorter spoken answer first and ask before expanding."


def test_reflection_why_mentions_class_without_copying_secrets() -> None:
    episode = _episode(
        summary="The task failed while using password=secret-value in unrelated context.",
        signals=(EpisodeSignal.TASK_FAILED,),
        outcome=EpisodeOutcome.FAILURE,
        evidence_refs=(EvidenceRef(kind="run", ref_id="run-secret", summary="bearer abcdefghijklmnopqrstuvwxyz"),),
    )

    reflection = ReflectionEngine().reflect(episode)

    assert "task_failed" in reflection.why_it_happened
    assert "failure" in reflection.why_it_happened
    assert "secret-value" not in reflection.why_it_happened
    assert "abcdefghijklmnopqrstuvwxyz" not in reflection.why_it_happened
    assert len(reflection.why_it_happened) < 500


def test_reflection_without_experience_has_empty_candidate_ids() -> None:
    reflection = ReflectionEngine().reflect(_episode())

    assert reflection.candidate_experience_ids == ()
