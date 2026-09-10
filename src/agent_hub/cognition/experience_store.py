from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from agent_hub.cognition.gates import LearningGateDecision, learning_gate_decision
from agent_hub.cognition.reflection import ReflectionEngine
from agent_hub.cognition.repository import CognitionRepository
from agent_hub.cognition.types import (
    CognitiveEpisode,
    CognitiveRecordStatus,
    EpisodeSignal,
    EvidenceRef,
    ExperienceKind,
    ExperienceRecord,
)


class EpisodeIngestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_stored: bool
    experience_created: bool
    rejection_reason: str | None = None
    experience: ExperienceRecord | None = None


class ExperienceStore:
    def __init__(self, repository: CognitionRepository) -> None:
        self._repository = repository

    async def record_episode(self, episode: CognitiveEpisode) -> EpisodeIngestResult:
        await self._repository.upsert("episode", str(episode.id), episode.model_dump(mode="json"))
        decision = learning_gate_decision(episode)
        if not decision.accepted:
            return EpisodeIngestResult(
                episode_stored=True,
                experience_created=False,
                rejection_reason=decision.reason.value,
            )

        experience = self._candidate_experience_from_episode(episode, decision)
        await self._save_experience(experience)
        reflection = ReflectionEngine().reflect(episode, experience)
        await self._repository.upsert(
            "reflection", str(reflection.id), reflection.model_dump(mode="json")
        )
        return EpisodeIngestResult(
            episode_stored=True,
            experience_created=True,
            experience=experience,
        )

    async def record_outcome(
        self, experience_id: UUID, succeeded: bool, evidence: EvidenceRef
    ) -> ExperienceRecord:
        experience = await self._load_experience(experience_id)
        now = _next_timestamp_after(experience.updated_at)
        confidence_delta = 0.05 if succeeded else -0.08
        updated = experience.model_copy(
            update={
                "usage_count": experience.usage_count + 1,
                "success_count": experience.success_count + (1 if succeeded else 0),
                "failure_count": experience.failure_count + (0 if succeeded else 1),
                "last_used_at": now,
                "last_verified_at": now if succeeded else experience.last_verified_at,
                "evidence_refs": (
                    (*experience.evidence_refs, evidence)
                    if succeeded
                    else experience.evidence_refs
                ),
                "contradictions": (
                    experience.contradictions
                    if succeeded
                    else (*experience.contradictions, evidence)
                ),
                "confidence": min(1.0, max(0.0, experience.confidence + confidence_delta)),
                "version": experience.version + 1,
                "updated_at": now,
            }
        )
        await self._save_experience(updated)
        return updated

    async def retire_experience(self, experience_id: UUID, reason: str) -> ExperienceRecord:
        status_by_reason = {
            "stale": CognitiveRecordStatus.STALE,
            "wrong": CognitiveRecordStatus.REJECTED,
            "unsafe": CognitiveRecordStatus.REJECTED,
        }
        if reason not in status_by_reason:
            raise ValueError("retirement reason must be one of: stale, unsafe, wrong")

        experience = await self._load_experience(experience_id)
        now = _next_timestamp_after(experience.updated_at)
        updated = experience.model_copy(
            update={
                "status": status_by_reason[reason],
                "version": experience.version + 1,
                "updated_at": now,
            }
        )
        await self._save_experience(updated)
        return updated

    def _candidate_experience_from_episode(
        self, episode: CognitiveEpisode, decision: LearningGateDecision
    ) -> ExperienceRecord:
        return ExperienceRecord(
            tenant_id=episode.tenant_id,
            user_id=episode.user_id,
            kind=_experience_kind_from_episode(episode),
            statement=episode.summary,
            applicability=_experience_applicability(episode),
            confidence=decision.confidence,
            evidence_refs=episode.evidence_refs,
            status=CognitiveRecordStatus.CANDIDATE,
        )

    async def _load_experience(self, experience_id: UUID) -> ExperienceRecord:
        payload = await self._repository.get("experience", str(experience_id))
        if payload is None:
            raise LookupError(f"experience {experience_id} was not found")
        return ExperienceRecord.model_validate(_record_payload(payload))

    async def _save_experience(self, experience: ExperienceRecord) -> None:
        await self._repository.upsert(
            "experience", str(experience.id), experience.model_dump(mode="json")
        )


def _experience_kind_from_episode(episode: CognitiveEpisode) -> ExperienceKind:
    signals = set(episode.signals)
    if {
        EpisodeSignal.USER_INTERRUPTED,
        EpisodeSignal.SPEECH_RECOGNITION_UNCERTAIN,
    } & signals:
        return ExperienceKind.VOICE_INTERACTION
    if {EpisodeSignal.USER_CORRECTED, EpisodeSignal.USER_REJECTED} & signals:
        return ExperienceKind.FAILURE_PATTERN
    if {EpisodeSignal.USER_SATISFIED, EpisodeSignal.TASK_SUCCEEDED} & signals:
        return ExperienceKind.SUCCESS_PATTERN
    return ExperienceKind.STRATEGY


def _experience_applicability(episode: CognitiveEpisode) -> str:
    if episode.conversation_id:
        return f"{episode.source.value} interaction in conversation {episode.conversation_id}"
    return f"{episode.source.value} interaction"


def _record_payload(payload: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in payload.items() if key != "record_type"}


def _next_timestamp_after(current: datetime) -> datetime:
    now = datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    if now <= current.astimezone(UTC):
        return current.astimezone(UTC) + timedelta(microseconds=1)
    return now
