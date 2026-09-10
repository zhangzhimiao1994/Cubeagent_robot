from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CognitiveSource(StrEnum):
    VOICE = "voice"
    WEB = "web"
    TASK = "task"
    DEVICE = "device"
    SYSTEM = "system"


class EpisodeSignal(StrEnum):
    USER_CORRECTED = "user_corrected"
    USER_REJECTED = "user_rejected"
    USER_SATISFIED = "user_satisfied"
    USER_INTERRUPTED = "user_interrupted"
    USER_REPEATED_QUESTION = "user_repeated_question"
    TASK_SUCCEEDED = "task_succeeded"
    TASK_FAILED = "task_failed"
    SPEECH_RECOGNITION_UNCERTAIN = "speech_recognition_uncertain"
    PLAYBACK_FAILED = "playback_failed"
    REPEATED_PATTERN = "repeated_pattern"


class EpisodeOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    NEUTRAL = "neutral"
    UNCERTAIN = "uncertain"


class ExperienceKind(StrEnum):
    PREFERENCE = "preference"
    STRATEGY = "strategy"
    FAILURE_PATTERN = "failure_pattern"
    SUCCESS_PATTERN = "success_pattern"
    RELATIONSHIP_PATTERN = "relationship_pattern"
    TOOL_PATTERN = "tool_pattern"
    VOICE_INTERACTION = "voice_interaction"
    WORLD_PATTERN = "world_pattern"


class CognitiveRecordStatus(StrEnum):
    ACTIVE = "active"
    CANDIDATE = "candidate"
    STALE = "stale"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class ReflectionType(StrEnum):
    CAUSAL = "causal"
    COUNTERFACTUAL = "counterfactual"
    POSITIVE = "positive"
    NEGATIVE = "negative"
    MIXED = "mixed"


class ReflectionTrigger(StrEnum):
    USER_CORRECTED = "user_corrected"
    USER_REJECTED = "user_rejected"
    USER_SATISFIED = "user_satisfied"
    TASK_SUCCEEDED = "task_succeeded"
    TASK_FAILED = "task_failed"
    REPEATED_PATTERN = "repeated_pattern"
    AGENT_UNCERTAIN = "agent_uncertain"
    SCHEDULED_REVIEW = "scheduled_review"


class BeliefStatus(StrEnum):
    ACTIVE = "active"
    CANDIDATE = "candidate"
    UNCERTAIN = "uncertain"
    CONTRADICTED = "contradicted"
    RETIRED = "retired"


class WorldEntityType(StrEnum):
    PERSON = "person"
    PROJECT = "project"
    TASK = "task"
    EVENT = "event"
    PLACE = "place"
    DEVICE = "device"
    TOPIC = "topic"


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1, max_length=64)
    ref_id: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=500)


class CognitiveEpisode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    user_id: UUID
    source: CognitiveSource
    conversation_id: str | None = Field(default=None, max_length=128)
    run_id: UUID | None = None
    started_at: datetime
    ended_at: datetime | None = None
    summary: str = Field(min_length=1, max_length=2000)
    signals: tuple[EpisodeSignal, ...] = Field(default_factory=tuple, max_length=24)
    outcome: EpisodeOutcome = EpisodeOutcome.NEUTRAL
    feedback: str = Field(default="", max_length=2000)
    evidence_refs: tuple[EvidenceRef, ...] = Field(default_factory=tuple, max_length=16)
    privacy_level: str = Field(default="normal", pattern=r"^(normal|sensitive|private)$")
    created_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())

    @model_validator(mode="after")
    def validate_episode_times(self) -> CognitiveEpisode:
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("episode ended_at must not be before started_at")
        return self


class ExperienceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    user_id: UUID
    kind: ExperienceKind
    statement: str = Field(min_length=1, max_length=1000)
    applicability: str = Field(min_length=1, max_length=1000)
    recommended_action: str = Field(default="", max_length=1000)
    avoid_action: str = Field(default="", max_length=1000)
    confidence: float = Field(default=0.5, ge=0, le=1)
    evidence_refs: tuple[EvidenceRef, ...] = Field(min_length=1, max_length=16)
    contradictions: tuple[EvidenceRef, ...] = Field(default_factory=tuple, max_length=16)
    usage_count: int = Field(default=0, ge=0)
    success_count: int = Field(default=0, ge=0)
    failure_count: int = Field(default=0, ge=0)
    last_used_at: datetime | None = None
    last_verified_at: datetime | None = None
    version: int = Field(default=1, ge=1)
    status: CognitiveRecordStatus = CognitiveRecordStatus.CANDIDATE
    created_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    updated_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())


class ReflectionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    episode_id: UUID
    reflection_type: ReflectionType
    trigger: ReflectionTrigger
    what_happened: str = Field(min_length=1, max_length=2000)
    why_it_happened: str = Field(min_length=1, max_length=2000)
    better_next_time: str = Field(min_length=1, max_length=2000)
    candidate_experience_ids: tuple[UUID, ...] = Field(default_factory=tuple, max_length=16)
    candidate_belief_updates: tuple[str, ...] = Field(default_factory=tuple, max_length=16)
    candidate_skill_updates: tuple[str, ...] = Field(default_factory=tuple, max_length=16)
    confidence: float = Field(default=0.5, ge=0, le=1)
    requires_approval: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())


class BeliefRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    user_id: UUID
    subject: str = Field(min_length=1, max_length=200)
    predicate: str = Field(min_length=1, max_length=120)
    object: str = Field(min_length=1, max_length=500)
    scope: str = Field(default="user", min_length=1, max_length=128)
    confidence: float = Field(default=0.45, ge=0, le=1)
    evidence_refs: tuple[EvidenceRef, ...] = Field(min_length=1, max_length=16)
    contradictions: tuple[EvidenceRef, ...] = Field(default_factory=tuple, max_length=16)
    last_verified_at: datetime | None = None
    verification_count: int = Field(default=0, ge=0)
    status: BeliefStatus = BeliefStatus.CANDIDATE
    created_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    updated_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())


class RelationshipState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    user_id: UUID
    familiarity: float = Field(default=0.0, ge=0, le=1)
    trust: float = Field(default=0.5, ge=0, le=1)
    rapport: float = Field(default=0.5, ge=0, le=1)
    preferred_tone: str = Field(default="direct", max_length=128)
    preferred_depth: str = Field(default="balanced", pattern=r"^(concise|balanced|detailed)$")
    interaction_rhythm: str = Field(default="user_led", max_length=128)
    shared_history: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    stable_preferences: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    recent_changes: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    boundaries: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    evidence_refs: tuple[EvidenceRef, ...] = Field(default_factory=tuple, max_length=32)
    last_updated_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())


class WorldStateItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    user_id: UUID
    entity_type: WorldEntityType
    name: str = Field(min_length=1, max_length=200)
    state: str = Field(min_length=1, max_length=1000)
    status: str = Field(default="active", pattern=r"^(active|pending|completed|cancelled|archived)$")
    starts_at: datetime | None = None
    due_at: datetime | None = None
    ended_at: datetime | None = None
    participants: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    evidence_refs: tuple[EvidenceRef, ...] = Field(min_length=1, max_length=16)
    confidence: float = Field(default=0.5, ge=0, le=1)
    last_verified_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    updated_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())


class SelfModelRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    user_id: UUID
    identity: str = Field(min_length=1, max_length=1000)
    personality: str = Field(min_length=1, max_length=1000)
    values: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    capability_boundaries: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    shared_story: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    version: int = Field(default=1, ge=1)
    protected: bool = True
    updated_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())


class ProtectedChangeProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    target: str = Field(min_length=1, max_length=128)
    proposed_change: str = Field(min_length=1, max_length=2000)
    evidence_refs: tuple[EvidenceRef, ...] = Field(min_length=1, max_length=16)
    requires_approval: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())


class CognitiveContextBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    core_constraints: tuple[str, ...] = Field(default_factory=tuple, max_length=1)
    relationship_context: tuple[str, ...] = Field(default_factory=tuple, max_length=3)
    world_context: tuple[str, ...] = Field(default_factory=tuple, max_length=2)
    experience_context: tuple[str, ...] = Field(default_factory=tuple, max_length=2)
    belief_context: tuple[str, ...] = Field(default_factory=tuple, max_length=3)
    skill_context: tuple[str, ...] = Field(default_factory=tuple, max_length=1)
    reasons: tuple[str, ...] = Field(default_factory=tuple, max_length=8)
