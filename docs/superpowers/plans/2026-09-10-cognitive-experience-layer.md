# Cognitive Experience Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a sparse, high-signal cognitive learning layer that turns selected interactions into reusable experience, reflection, beliefs, relationship state, world state, and skill improvement proposals.

**Architecture:** Add a new `src/agent_hub/cognition/` package with typed domain models, learning gates, persistence, services, router, and integration adapters. The first implementation persists typed cognitive records through `AdminResourceRow(kind="cognition")` to avoid introducing many tables before the model stabilizes, while still keeping strict tenant/user isolation and typed payload validation.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, SQLAlchemy async, Alembic, pytest, React, TypeScript, Zod, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-10-cognitive-experience-layer-design.md`

## Global Constraints

- The goal is not to remember more raw content; the goal is to extract the few important parts, compress them into stable and reviewable structures, verify them over time, forget weak or stale conclusions, and retrieve only the most relevant items for the current situation.
- Ordinary chat remains short-lived.
- Raw transcripts remain run or episode evidence, not direct strategy.
- Only important, repeated, corrected, successful, failed, or relationship-relevant patterns can enter long-term cognitive storage.
- Long-term items must remain small, structured, source-backed, confidence-scored, and eligible for decay or replacement.
- Retrieval must be dynamic and bounded.
- Do not replace Hermes, Memory, Skill, or Evolution.
- Do not introduce several overlapping third-party memory frameworks.
- Ordinary reflection cannot directly rewrite core identity, safety rules, or tool permissions.
- Protected changes must go through explicit approval, versioning, audit, and rollback.
- Every cognitive record must preserve tenant and user isolation.
- Secrets, credentials, tokens, prompt-like external content, and unsupported sensitive-attribute guesses must be rejected.

---

## File Structure

Create backend cognition package:

- `src/agent_hub/cognition/__init__.py`: public exports.
- `src/agent_hub/cognition/types.py`: Pydantic domain records and enums.
- `src/agent_hub/cognition/gates.py`: deterministic sparse-learning gates and rejection reasons.
- `src/agent_hub/cognition/repository.py`: repository protocol, in-memory repository, and SQL admin-resource repository.
- `src/agent_hub/cognition/experience_store.py`: episode ingestion and experience lifecycle operations.
- `src/agent_hub/cognition/reflection.py`: deterministic first-pass reflection engine.
- `src/agent_hub/cognition/state.py`: belief, relationship, world-state, and self-model update services.
- `src/agent_hub/cognition/router.py`: bounded Memory/Experience context selection.
- `src/agent_hub/cognition/integrations.py`: Hermes, Evolution, Skill, and Memory integration helpers.
- `src/agent_hub/cognition/runtime.py`: best-effort runtime advice and outcome ingestion boundary.
- `src/agent_hub/api/routers/cognition.py`: admin API for debugging and operations.

Modify backend:

- `src/agent_hub/db/models.py`: allow `AdminResourceRow.kind == "cognition"`.
- `alembic/versions/0020_cognition_admin_resources.py`: update check constraint for the new kind.
- `src/agent_hub/app.py`: import and mount the cognition router.
- `src/agent_hub/auth/models.py`: add `cognition:read` and `cognition:write` permissions for admin/operator roles using the existing permission style.

Create backend tests:

- `tests/unit/cognition/test_types.py`
- `tests/unit/cognition/test_gates.py`
- `tests/unit/cognition/test_repository.py`
- `tests/unit/cognition/test_experience_store.py`
- `tests/unit/cognition/test_reflection.py`
- `tests/unit/cognition/test_state.py`
- `tests/unit/cognition/test_router.py`
- `tests/unit/cognition/test_integrations.py`
- `tests/unit/runtime/test_cognitive_context.py`
- `tests/api/test_cognition_api.py`
- `tests/integration/cognition/test_cognition_persistence.py`
- `tests/security/test_cognition_safety.py`

Modify frontend:

- `web/src/api/client.ts`: Zod schemas and API methods for cognition records.
- `web/src/app/router.tsx`: add `/cognition`.
- `web/src/app/navSections.ts`: add cognition debug navigation.
- `web/src/pages/CognitionPage.tsx`: operational debug UI.
- `web/src/pages/CognitionPage.test.tsx`: render, filtering, and router-preview tests.

---

### Task 1: Domain Types And Learning Gates

**Files:**
- Create: `src/agent_hub/cognition/__init__.py`
- Create: `src/agent_hub/cognition/types.py`
- Create: `src/agent_hub/cognition/gates.py`
- Test: `tests/unit/cognition/test_types.py`
- Test: `tests/unit/cognition/test_gates.py`

**Interfaces:**
- Produces: `CognitiveEpisode`, `ExperienceRecord`, `ReflectionRecord`, `BeliefRecord`, `RelationshipState`, `WorldStateItem`, `SelfModelRecord`, `CognitiveContextBundle`.
- Produces: `learning_gate_decision(episode: CognitiveEpisode) -> LearningGateDecision`.
- Produces: `rejects_unsafe_text(text: str) -> bool`.

- [ ] **Step 1: Write failing type validation tests**

```python
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from agent_hub.cognition.types import (
    CognitiveEpisode,
    CognitiveSource,
    EpisodeOutcome,
    EpisodeSignal,
    EvidenceRef,
    ExperienceKind,
    ExperienceRecord,
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
```

- [ ] **Step 2: Run the tests and confirm the expected failure**

Run: `pytest tests/unit/cognition/test_types.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'agent_hub.cognition'`.

- [ ] **Step 3: Implement `types.py`**

Create enums and Pydantic records with these exact class names and fields:

```python
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
```

Add the remaining records in the same file:

```python
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
```

- [ ] **Step 4: Write failing gate tests**

```python
from datetime import UTC, datetime
from uuid import uuid4

from agent_hub.cognition.gates import LearningGateReason, learning_gate_decision
from agent_hub.cognition.types import CognitiveEpisode, CognitiveSource, EpisodeOutcome, EpisodeSignal, EvidenceRef


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
```

- [ ] **Step 5: Implement `gates.py`**

```python
from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

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


class LearningGateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool
    reason: LearningGateReason
    confidence: float


def rejects_unsafe_text(text: str) -> bool:
    lowered = text.casefold()
    if "ignore previous instructions" in lowered or "system prompt" in lowered:
        return True
    return any(pattern.search(text) is not None for pattern in _SECRET_PATTERNS)


def learning_gate_decision(episode: CognitiveEpisode) -> LearningGateDecision:
    if rejects_unsafe_text(episode.summary) or rejects_unsafe_text(episode.feedback):
        return LearningGateDecision(accepted=False, reason=LearningGateReason.UNSAFE_CONTENT, confidence=1.0)
    if EpisodeSignal.SPEECH_RECOGNITION_UNCERTAIN in episode.signals and len(episode.signals) == 1:
        return LearningGateDecision(accepted=False, reason=LearningGateReason.LOW_CONFIDENCE_ASR, confidence=0.85)
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
```

- [ ] **Step 6: Run focused tests**

Run: `pytest tests/unit/cognition/test_types.py tests/unit/cognition/test_gates.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/agent_hub/cognition/__init__.py src/agent_hub/cognition/types.py src/agent_hub/cognition/gates.py tests/unit/cognition/test_types.py tests/unit/cognition/test_gates.py
git commit -m "feat: add cognition domain types and gates"
```

---

### Task 2: Cognition Persistence Through Admin Resources

**Files:**
- Create: `src/agent_hub/cognition/repository.py`
- Modify: `src/agent_hub/db/models.py`
- Create: `alembic/versions/0020_cognition_admin_resources.py`
- Test: `tests/unit/cognition/test_repository.py`
- Test: `tests/integration/cognition/test_cognition_persistence.py`

**Interfaces:**
- Consumes: `CognitiveEpisode`, `ExperienceRecord`, `ReflectionRecord`, `BeliefRecord`, `RelationshipState`, `WorldStateItem`, `SelfModelRecord`.
- Produces: `CognitionRepository` protocol with `upsert(record_type: str, record_id: str, payload: dict[str, object])`, `get(record_type: str, record_id: str)`, `list(record_type: str | None = None)`, and `delete(record_type: str, record_id: str)`.
- Produces: `InMemoryCognitionRepository`.
- Produces: `AdminResourceCognitionRepository`.

- [ ] **Step 1: Write failing repository tests**

```python
from uuid import uuid4

import pytest

from agent_hub.cognition.repository import InMemoryCognitionRepository


@pytest.mark.asyncio
async def test_in_memory_repository_isolates_tenant_and_user() -> None:
    tenant_a = uuid4()
    tenant_b = uuid4()
    user_a = uuid4()
    user_b = uuid4()
    repo_a = InMemoryCognitionRepository(tenant_id=tenant_a, user_id=user_a)
    repo_b = InMemoryCognitionRepository(tenant_id=tenant_b, user_id=user_b)

    payload = {"record_type": "experience", "id": "exp-1", "statement": "Use concise voice replies."}
    await repo_a.upsert("experience", "exp-1", payload)

    assert await repo_a.get("experience", "exp-1") == payload
    assert await repo_b.get("experience", "exp-1") is None
```

- [ ] **Step 2: Run the repository test and confirm the expected failure**

Run: `pytest tests/unit/cognition/test_repository.py -v`

Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `agent_hub.cognition.repository`.

- [ ] **Step 3: Implement repository protocol and in-memory repository**

```python
from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Protocol
from uuid import UUID


class CognitionRepository(Protocol):
    async def upsert(self, record_type: str, record_id: str, payload: dict[str, object]) -> dict[str, object]: ...
    async def get(self, record_type: str, record_id: str) -> dict[str, object] | None: ...
    async def list(self, record_type: str | None = None) -> tuple[dict[str, object], ...]: ...
    async def delete(self, record_type: str, record_id: str) -> bool: ...


class InMemoryCognitionRepository:
    def __init__(self, *, tenant_id: UUID, user_id: UUID) -> None:
        self._tenant_id = tenant_id
        self._user_id = user_id
        self._records: dict[tuple[UUID, UUID, str, str], dict[str, object]] = {}
        self._lock = asyncio.Lock()

    async def upsert(self, record_type: str, record_id: str, payload: dict[str, object]) -> dict[str, object]:
        normalized = _payload(record_type, record_id, payload)
        async with self._lock:
            self._records[(self._tenant_id, self._user_id, record_type, record_id)] = normalized
        return normalized

    async def get(self, record_type: str, record_id: str) -> dict[str, object] | None:
        async with self._lock:
            found = self._records.get((self._tenant_id, self._user_id, record_type, record_id))
            return dict(found) if found is not None else None

    async def list(self, record_type: str | None = None) -> tuple[dict[str, object], ...]:
        async with self._lock:
            rows = [
                dict(payload)
                for (tenant_id, user_id, found_type, _), payload in self._records.items()
                if tenant_id == self._tenant_id
                and user_id == self._user_id
                and (record_type is None or found_type == record_type)
            ]
        return tuple(rows)

    async def delete(self, record_type: str, record_id: str) -> bool:
        async with self._lock:
            return self._records.pop((self._tenant_id, self._user_id, record_type, record_id), None) is not None


def _payload(record_type: str, record_id: str, payload: Mapping[str, object]) -> dict[str, object]:
    normalized = dict(payload)
    normalized["record_type"] = record_type
    normalized["id"] = record_id
    return normalized
```

- [ ] **Step 4: Update admin resource kind constraint**

Modify `src/agent_hub/db/models.py` check constraint string to include `'cognition'`:

```python
"kind IN ('workflow', 'agent', 'main_agent', 'skill', 'mcp', 'memory', 'hermes', 'audit', 'log', 'setting', 'channel', 'openclaw', 'openclaw_session', 'schedule', 'evolution', 'cognition')"
```

- [ ] **Step 5: Add Alembic migration**

Create `alembic/versions/0020_cognition_admin_resources.py`:

```python
"""allow cognition admin resources

Revision ID: 0020_cognition_admin_resources
Revises: 0019_run_actor_role
Create Date: 2026-09-10 00:00:00.000000
"""

from alembic import op

revision = "0020_cognition_admin_resources"
down_revision = "0019_run_actor_role"
branch_labels = None
depends_on = None

_OLD = "kind IN ('workflow', 'agent', 'main_agent', 'skill', 'mcp', 'memory', 'hermes', 'audit', 'log', 'setting', 'channel', 'openclaw', 'openclaw_session', 'schedule', 'evolution')"
_NEW = "kind IN ('workflow', 'agent', 'main_agent', 'skill', 'mcp', 'memory', 'hermes', 'audit', 'log', 'setting', 'channel', 'openclaw', 'openclaw_session', 'schedule', 'evolution', 'cognition')"


def upgrade() -> None:
    op.drop_constraint("ck_agent_hub_admin_resources_kind", "agent_hub_admin_resources", type_="check")
    op.create_check_constraint("ck_agent_hub_admin_resources_kind", "agent_hub_admin_resources", _NEW)


def downgrade() -> None:
    op.execute("DELETE FROM agent_hub_admin_resources WHERE kind = 'cognition'")
    op.drop_constraint("ck_agent_hub_admin_resources_kind", "agent_hub_admin_resources", type_="check")
    op.create_check_constraint("ck_agent_hub_admin_resources_kind", "agent_hub_admin_resources", _OLD)
```

- [ ] **Step 6: Implement SQL repository**

Add `AdminResourceCognitionRepository` in `repository.py`. It must use `AdminResourceRow.kind == "cognition"` and encode `record_type` into `resource_id` as `{record_type}:{record_id}`.

```python
from collections.abc import Callable
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_hub.db.models import AdminResourceRow


class AdminResourceCognitionRepository:
    def __init__(
        self,
        *,
        session_factory: Callable[[], AsyncSession],
        tenant_id: UUID,
        user_id: UUID,
    ) -> None:
        self._session_factory = session_factory
        self._tenant_id = tenant_id
        self._user_id = user_id

    async def upsert(self, record_type: str, record_id: str, payload: dict[str, object]) -> dict[str, object]:
        normalized = _payload(record_type, record_id, payload)
        normalized["tenant_id"] = str(self._tenant_id)
        normalized["user_id"] = str(self._user_id)
        resource_id = _resource_id(record_type, record_id)
        async with self._session_factory() as session:
            result = await session.execute(
                select(AdminResourceRow)
                .where(AdminResourceRow.tenant_id == self._tenant_id)
                .where(AdminResourceRow.kind == "cognition")
                .where(AdminResourceRow.resource_id == resource_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                session.add(AdminResourceRow(tenant_id=self._tenant_id, kind="cognition", resource_id=resource_id, payload=normalized))
            else:
                row.payload = normalized
            await session.commit()
        return normalized


def _resource_id(record_type: str, record_id: str) -> str:
    return f"{record_type}:{record_id}"
```

Implement `get`, `list`, and `delete` using the same resource id encoding. `list` must filter returned payloads by `payload["user_id"] == str(self._user_id)`.

- [ ] **Step 7: Run persistence tests**

Run: `pytest tests/unit/cognition/test_repository.py tests/integration/cognition/test_cognition_persistence.py -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/agent_hub/cognition/repository.py src/agent_hub/db/models.py alembic/versions/0020_cognition_admin_resources.py tests/unit/cognition/test_repository.py tests/integration/cognition/test_cognition_persistence.py
git commit -m "feat: persist cognition records"
```

---

### Task 3: Experience Store Lifecycle

**Files:**
- Create: `src/agent_hub/cognition/experience_store.py`
- Test: `tests/unit/cognition/test_experience_store.py`

**Interfaces:**
- Consumes: `CognitionRepository`, `CognitiveEpisode`, `ExperienceRecord`, `LearningGateDecision`.
- Produces: `ExperienceStore.record_episode(episode: CognitiveEpisode) -> EpisodeIngestResult`.
- Produces: `ExperienceStore.record_outcome(experience_id: UUID, succeeded: bool, evidence: EvidenceRef) -> ExperienceRecord`.
- Produces: `ExperienceStore.retire_experience(experience_id: UUID, reason: str) -> ExperienceRecord`.

- [ ] **Step 1: Write failing lifecycle tests**

```python
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from agent_hub.cognition.experience_store import ExperienceStore
from agent_hub.cognition.repository import InMemoryCognitionRepository
from agent_hub.cognition.types import CognitiveEpisode, CognitiveSource, EpisodeSignal, EvidenceRef


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
    assert result.experience.kind.value == "voice_interaction"
    assert result.experience.status.value == "candidate"
```

- [ ] **Step 2: Run and confirm failure**

Run: `pytest tests/unit/cognition/test_experience_store.py -v`

Expected: FAIL with `ImportError` for `ExperienceStore`.

- [ ] **Step 3: Implement episode ingest result and store**

```python
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from agent_hub.cognition.gates import learning_gate_decision
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
        experience = _candidate_experience_from_episode(episode, confidence=decision.confidence)
        await self._repository.upsert("experience", str(experience.id), experience.model_dump(mode="json"))
        return EpisodeIngestResult(episode_stored=True, experience_created=True, experience=experience)
```

Implement `_candidate_experience_from_episode` with deterministic mapping:

- `USER_INTERRUPTED` or `SPEECH_RECOGNITION_UNCERTAIN` -> `ExperienceKind.VOICE_INTERACTION`.
- `USER_CORRECTED` or `USER_REJECTED` -> `ExperienceKind.FAILURE_PATTERN`.
- `USER_SATISFIED` or `TASK_SUCCEEDED` -> `ExperienceKind.SUCCESS_PATTERN`.
- default accepted pattern -> `ExperienceKind.STRATEGY`.

- [ ] **Step 4: Implement outcome updates**

`record_outcome` must increment `usage_count`, increment success/failure count, update `last_used_at`, set `last_verified_at` on success, and adjust confidence by `+0.05` on success or `-0.08` on failure with bounds `[0, 1]`.

- [ ] **Step 5: Implement retirement**

`retire_experience` must load the experience, set `status=STALE` when reason is `"stale"` and `status=REJECTED` for `"wrong"` or `"unsafe"`, increment `version`, and persist the updated record.

- [ ] **Step 6: Run focused tests**

Run: `pytest tests/unit/cognition/test_experience_store.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/agent_hub/cognition/experience_store.py tests/unit/cognition/test_experience_store.py
git commit -m "feat: add experience store lifecycle"
```

---

### Task 4: Reflection Engine

**Files:**
- Create: `src/agent_hub/cognition/reflection.py`
- Test: `tests/unit/cognition/test_reflection.py`

**Interfaces:**
- Consumes: `CognitiveEpisode`, `ExperienceRecord`, `EpisodeSignal`, `EpisodeOutcome`.
- Produces: `ReflectionEngine.reflect(episode: CognitiveEpisode, experience: ExperienceRecord | None = None) -> ReflectionRecord`.

- [ ] **Step 1: Write failing reflection tests**

```python
from datetime import UTC, datetime
from uuid import uuid4

from agent_hub.cognition.reflection import ReflectionEngine
from agent_hub.cognition.types import CognitiveEpisode, CognitiveSource, EpisodeOutcome, EpisodeSignal, EvidenceRef, ReflectionType


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
```

- [ ] **Step 2: Run and confirm failure**

Run: `pytest tests/unit/cognition/test_reflection.py -v`

Expected: FAIL with `ImportError` for `ReflectionEngine`.

- [ ] **Step 3: Implement deterministic reflection**

```python
from __future__ import annotations

from agent_hub.cognition.types import (
    CognitiveEpisode,
    EpisodeOutcome,
    EpisodeSignal,
    ExperienceRecord,
    ReflectionRecord,
    ReflectionTrigger,
    ReflectionType,
)


class ReflectionEngine:
    def reflect(
        self,
        episode: CognitiveEpisode,
        experience: ExperienceRecord | None = None,
    ) -> ReflectionRecord:
        reflection_type = _reflection_type(episode)
        trigger = _trigger(episode)
        return ReflectionRecord(
            episode_id=episode.id,
            reflection_type=reflection_type,
            trigger=trigger,
            what_happened=episode.summary,
            why_it_happened=_why(episode),
            better_next_time=_better_next_time(episode),
            candidate_experience_ids=(experience.id,) if experience is not None else (),
            confidence=0.72 if episode.evidence_refs else 0.45,
            requires_approval=False,
        )
```

Mapping rules:

- failed outcome or `TASK_FAILED` -> `COUNTERFACTUAL`, trigger `TASK_FAILED`.
- `USER_CORRECTED` -> `NEGATIVE`, trigger `USER_CORRECTED`.
- `USER_SATISFIED` or success outcome -> `POSITIVE`, trigger `USER_SATISFIED` or `TASK_SUCCEEDED`.
- repeated pattern -> `CAUSAL`, trigger `REPEATED_PATTERN`.
- otherwise -> `MIXED`, trigger `AGENT_UNCERTAIN`.

`_better_next_time` must produce bounded actionable text. If the summary mentions "long" and source is voice, return: `Use a shorter spoken answer first and ask before expanding.` If the summary mentions "health check", return: `Run or verify the health check before reporting deployment success.`

- [ ] **Step 4: Persist reflections in ExperienceStore**

Modify `ExperienceStore.record_episode` to call `ReflectionEngine().reflect(episode, experience)` and persist the reflection with `record_type="reflection"` whenever an experience is created.

- [ ] **Step 5: Run focused tests**

Run: `pytest tests/unit/cognition/test_reflection.py tests/unit/cognition/test_experience_store.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/agent_hub/cognition/reflection.py src/agent_hub/cognition/experience_store.py tests/unit/cognition/test_reflection.py tests/unit/cognition/test_experience_store.py
git commit -m "feat: add cognitive reflection engine"
```

---

### Task 5: Belief, Relationship, World State, And Self Model Services

**Files:**
- Create: `src/agent_hub/cognition/state.py`
- Test: `tests/unit/cognition/test_state.py`

**Interfaces:**
- Consumes: `CognitionRepository`, `EvidenceRef`, `ExperienceRecord`, `ReflectionRecord`.
- Produces: `BeliefService.upsert_belief(...) -> BeliefRecord`.
- Produces: `BeliefService.apply_contradiction(...) -> BeliefRecord`.
- Produces: `RelationshipService.update_from_experience(experience: ExperienceRecord) -> RelationshipState`.
- Produces: `WorldStateService.upsert_item(item: WorldStateItem) -> WorldStateItem`.
- Produces: `SelfModelService.propose_change(...) -> ProtectedChangeProposal`.

- [ ] **Step 1: Write failing state tests**

```python
from uuid import uuid4

import pytest

from agent_hub.cognition.repository import InMemoryCognitionRepository
from agent_hub.cognition.state import BeliefService, RelationshipService
from agent_hub.cognition.types import BeliefStatus, EvidenceRef


@pytest.mark.asyncio
async def test_belief_confidence_increases_and_decreases_with_evidence() -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    service = BeliefService(InMemoryCognitionRepository(tenant_id=tenant_id, user_id=user_id))
    evidence = EvidenceRef(kind="experience", ref_id="exp-1", summary="user accepted short voice answer")

    belief = await service.upsert_belief(
        tenant_id=tenant_id,
        user_id=user_id,
        subject="user",
        predicate="prefers",
        object="short voice replies during debugging",
        scope="voice_debugging",
        evidence=evidence,
    )
    contradicted = await service.apply_contradiction(
        belief.id,
        EvidenceRef(kind="experience", ref_id="exp-2", summary="user requested detailed explanation"),
    )

    assert belief.status is BeliefStatus.CANDIDATE
    assert contradicted.confidence < belief.confidence
    assert contradicted.contradictions
```

- [ ] **Step 2: Run and confirm failure**

Run: `pytest tests/unit/cognition/test_state.py -v`

Expected: FAIL with `ImportError` for `BeliefService`.

- [ ] **Step 3: Implement belief service**

`upsert_belief` must search existing belief payloads for the same `subject`, `predicate`, `object`, and `scope`. If found, append evidence, increase confidence by `0.07`, increment verification count, update `last_verified_at`, and keep `status=ACTIVE` once confidence is at least `0.75`. If not found, create `BeliefRecord(status=CANDIDATE, confidence=0.45)`.

`apply_contradiction` must append contradiction evidence, lower confidence by `0.15`, and set `status=CONTRADICTED` below `0.35`; otherwise set `status=UNCERTAIN`.

- [ ] **Step 4: Implement relationship service**

`RelationshipService.update_from_experience` must update one user-level `RelationshipState` record:

- `VOICE_INTERACTION` with recommended short replies sets `preferred_depth="concise"`.
- successful repeated interaction raises `familiarity` and `trust` by `0.03`.
- failed interaction lowers `trust` by `0.04`.
- every update appends an evidence ref and caps scores between `0` and `1`.

- [ ] **Step 5: Implement world state service**

`WorldStateService.upsert_item` must store `WorldStateItem` by id and reject records without evidence. `mark_status(item_id, status, evidence)` must update `status`, append evidence, and set `last_verified_at`.

- [ ] **Step 6: Implement protected self-model proposals**

`SelfModelService.propose_change` must create a `ProtectedChangeProposal` with `requires_approval=True`. It must not mutate `SelfModelRecord` directly.

- [ ] **Step 7: Run focused tests**

Run: `pytest tests/unit/cognition/test_state.py -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/agent_hub/cognition/state.py tests/unit/cognition/test_state.py
git commit -m "feat: add cognitive state services"
```

---

### Task 6: Memory And Experience Router

**Files:**
- Create: `src/agent_hub/cognition/router.py`
- Modify: `src/agent_hub/context/builder.py`
- Test: `tests/unit/cognition/test_router.py`
- Test: `tests/unit/context/test_builder.py`

**Interfaces:**
- Consumes: `CognitionRepository`.
- Produces: `MemoryExperienceRouter.build_context_bundle(scene: str, current_request: str, limit: int = 8) -> CognitiveContextBundle`.
- Produces: `render_cognitive_context(bundle: CognitiveContextBundle) -> str`.
- Modifies: `ContextBuildInput` to accept `cognitive_context: str | None = None`.

- [ ] **Step 1: Write failing router tests**

```python
from uuid import uuid4

import pytest

from agent_hub.cognition.repository import InMemoryCognitionRepository
from agent_hub.cognition.router import MemoryExperienceRouter, render_cognitive_context
from agent_hub.cognition.types import CognitiveRecordStatus, EvidenceRef, ExperienceKind, ExperienceRecord


@pytest.mark.asyncio
async def test_router_returns_bounded_relevant_experience_context() -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    repo = InMemoryCognitionRepository(tenant_id=tenant_id, user_id=user_id)
    evidence = EvidenceRef(kind="episode", ref_id="ep-1", summary="voice correction")
    for index in range(5):
        record = ExperienceRecord(
            tenant_id=tenant_id,
            user_id=user_id,
            kind=ExperienceKind.VOICE_INTERACTION,
            statement=f"Voice deployment experience {index}",
            applicability="voice deployment debugging",
            recommended_action="Keep spoken answers short.",
            confidence=0.8,
            evidence_refs=(evidence,),
            status=CognitiveRecordStatus.ACTIVE,
        )
        await repo.upsert("experience", str(record.id), record.model_dump(mode="json"))

    bundle = await MemoryExperienceRouter(repo).build_context_bundle(
        scene="voice_chat",
        current_request="deployment debugging",
        limit=3,
    )

    assert len(bundle.experience_context) == 3
    assert "Voice deployment experience" in render_cognitive_context(bundle)
```

- [ ] **Step 2: Run and confirm failure**

Run: `pytest tests/unit/cognition/test_router.py -v`

Expected: FAIL with `ImportError` for `MemoryExperienceRouter`.

- [ ] **Step 3: Implement router scoring**

Router scoring rules:

- reject records not `ACTIVE` or `CANDIDATE`.
- add `40` for term overlap between `current_request` and `statement` or `applicability`.
- add `25` when scene is `voice_chat` and kind is `VOICE_INTERACTION`.
- add `int(confidence * 20)`.
- subtract `30` if contradictions are present and confidence is below `0.6`.
- sort by score descending, then `updated_at` descending.

Bounded output:

- max 1 self/core constraint block.
- max 3 relationship or preference items.
- max 2 world items.
- max 2 experience items by default.
- max 1 skill recommendation.

- [ ] **Step 4: Add cognitive context to ContextBuilder**

Modify `ContextBuildInput`:

```python
cognitive_context: str | None = None
```

In `_candidate_sections`, add it after current constraints and before regular memory:

```python
if value.cognitive_context:
    sections.append(_section("cognitive_context", value.cognitive_context, 55))
```

- [ ] **Step 5: Add context builder test**

```python
from agent_hub.context.builder import ContextBuilder, ContextBuildInput


def test_context_builder_includes_bounded_cognitive_context() -> None:
    built = ContextBuilder().build(
        ContextBuildInput(
            system_policy="policy",
            current_user_request="debug voice robot",
            cognitive_context="<COGNITIVE_CONTEXT>[]</COGNITIVE_CONTEXT>",
        ),
        token_budget=200,
    )

    assert any(section.name == "cognitive_context" for section in built.sections)
```

- [ ] **Step 6: Run focused tests**

Run: `pytest tests/unit/cognition/test_router.py tests/unit/context/test_builder.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/agent_hub/cognition/router.py src/agent_hub/context/builder.py tests/unit/cognition/test_router.py tests/unit/context/test_builder.py
git commit -m "feat: route cognitive context"
```

---

### Task 7: Hermes, Evolution, Skill, And Memory Integrations

**Files:**
- Create: `src/agent_hub/cognition/integrations.py`
- Test: `tests/unit/cognition/test_integrations.py`

**Interfaces:**
- Consumes: `ExperienceRecord`, `ReflectionRecord`, `BeliefRecord`, `EvolutionRunRequest`, `HermesFeedbackRequest` payload shape.
- Produces: `hermes_feedback_from_experience(experience: ExperienceRecord) -> dict[str, object]`.
- Produces: `evolution_request_from_experiences(experiences: tuple[ExperienceRecord, ...]) -> EvolutionRunRequest | None`.
- Produces: `memory_candidate_from_belief(belief: BeliefRecord) -> dict[str, object] | None`.

- [ ] **Step 1: Write failing integration tests**

```python
from uuid import uuid4

from agent_hub.cognition.integrations import evolution_request_from_experiences, hermes_feedback_from_experience
from agent_hub.cognition.types import CognitiveRecordStatus, EvidenceRef, ExperienceKind, ExperienceRecord


def test_hermes_feedback_from_experience_is_bounded() -> None:
    exp = ExperienceRecord(
        tenant_id=uuid4(),
        user_id=uuid4(),
        kind=ExperienceKind.STRATEGY,
        statement="Short deployment answers work better in voice mode.",
        applicability="voice deployment debugging",
        recommended_action="Give one step first.",
        confidence=0.82,
        evidence_refs=(EvidenceRef(kind="episode", ref_id="ep-1", summary="accepted concise answer"),),
        status=CognitiveRecordStatus.ACTIVE,
    )

    payload = hermes_feedback_from_experience(exp)

    assert payload["category"] == "conversation"
    assert payload["outcome"] == "success"
    assert payload["weight"] >= 1
    assert "Short deployment answers" in str(payload["lesson"])


def test_evolution_request_requires_repeated_success() -> None:
    evidence = EvidenceRef(kind="episode", ref_id="ep-1", summary="success")
    exp = ExperienceRecord(
        tenant_id=uuid4(),
        user_id=uuid4(),
        kind=ExperienceKind.TOOL_PATTERN,
        statement="A robot diagnostics workflow works well.",
        applicability="device troubleshooting",
        recommended_action="Run diagnostics before reconnecting.",
        confidence=0.86,
        evidence_refs=(evidence,),
        usage_count=5,
        success_count=4,
        failure_count=0,
        status=CognitiveRecordStatus.ACTIVE,
    )

    request = evolution_request_from_experiences((exp,))

    assert request is not None
    assert request.kind == "skill_optimization"
    assert request.approval_policy == "ask"
```

- [ ] **Step 2: Run and confirm failure**

Run: `pytest tests/unit/cognition/test_integrations.py -v`

Expected: FAIL with `ImportError` for `agent_hub.cognition.integrations`.

- [ ] **Step 3: Implement Hermes adapter**

`hermes_feedback_from_experience` returns:

```python
{
    "category": "conversation",
    "outcome": "success" if experience.success_count >= experience.failure_count else "failure",
    "lesson": f"{experience.statement} Recommended action: {experience.recommended_action}",
    "tags": [experience.kind.value, "cognition"],
    "weight": max(1, min(10, int(round(experience.confidence * 10)))),
}
```

Do not include raw transcript or secret-like evidence details.

- [ ] **Step 4: Implement Evolution adapter**

`evolution_request_from_experiences` returns `None` unless at least one active experience has:

- `usage_count >= 3`
- `success_count >= 3`
- `failure_count == 0`
- `confidence >= 0.8`
- kind `STRATEGY`, `TOOL_PATTERN`, or `SUCCESS_PATTERN`

When eligible, return `EvolutionRunRequest(kind="skill_optimization", title="Cognitive skill improvement", objective=..., approval_policy="ask", iteration_policy="score_gated", memory_policy="summarize_between_rounds", max_rounds=3, min_delta=2.0, rubric=[...])`.

- [ ] **Step 5: Implement Memory adapter**

`memory_candidate_from_belief` returns `None` for beliefs below confidence `0.75`, contradicted beliefs, and sensitive scopes. For eligible beliefs, return a bounded dict with `layer="episodic"`, `category="fact"`, `text`, `confidence`, and `metadata={"source": "cognition_belief"}`.

- [ ] **Step 6: Run focused tests**

Run: `pytest tests/unit/cognition/test_integrations.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/agent_hub/cognition/integrations.py tests/unit/cognition/test_integrations.py
git commit -m "feat: connect cognition to learning systems"
```

---

### Task 8: Runtime Advice And Outcome Hook

**Files:**
- Create: `src/agent_hub/cognition/runtime.py`
- Modify: `src/agent_hub/runs/service.py`
- Test: `tests/unit/runtime/test_cognitive_context.py`
- Test: `tests/unit/runs/test_conversation_mode.py`

**Interfaces:**
- Consumes: `MemoryExperienceRouter`, `CognitiveContextBundle`, `render_cognitive_context`, completed run status, routing decision payloads.
- Produces: `CognitiveAdvisorProtocol.advise(...) -> CognitiveContextBundle`.
- Produces: `safe_cognitive_context_text(...) -> str`.
- Modifies: `RunService` to call cognitive advice as best-effort context, with timeout and failure isolation similar to Hermes.

- [ ] **Step 1: Write failing runtime advice tests**

```python
import asyncio
from uuid import uuid4

import pytest

from agent_hub.cognition.runtime import safe_cognitive_context_text
from agent_hub.cognition.types import CognitiveContextBundle


class SlowCognitiveAdvisor:
    async def advise(self, **kwargs):
        await asyncio.sleep(2)
        return CognitiveContextBundle()


class WorkingCognitiveAdvisor:
    async def advise(self, **kwargs):
        return CognitiveContextBundle(
            experience_context=("Use concise spoken deployment guidance.",),
            relationship_context=("User prefers direct debugging steps.",),
        )


@pytest.mark.asyncio
async def test_safe_cognitive_context_times_out_without_blocking() -> None:
    text = await safe_cognitive_context_text(
        SlowCognitiveAdvisor(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        scene="voice_chat",
        current_request="debug deployment",
        timeout_seconds=0.01,
    )

    assert text == ""


@pytest.mark.asyncio
async def test_safe_cognitive_context_formats_bounded_payload() -> None:
    text = await safe_cognitive_context_text(
        WorkingCognitiveAdvisor(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        scene="voice_chat",
        current_request="debug deployment",
        timeout_seconds=0.2,
    )

    assert text.startswith("<COGNITIVE_CONTEXT>")
    assert "Use concise spoken deployment guidance." in text
```

- [ ] **Step 2: Run and confirm failure**

Run: `pytest tests/unit/runtime/test_cognitive_context.py -v`

Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `agent_hub.cognition.runtime`.

- [ ] **Step 3: Implement runtime boundary**

```python
from __future__ import annotations

import asyncio
from typing import Protocol
from uuid import UUID

from agent_hub.cognition.router import render_cognitive_context
from agent_hub.cognition.types import CognitiveContextBundle


class CognitiveAdvisorProtocol(Protocol):
    async def advise(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        scene: str,
        current_request: str,
        conversation_id: str | None = None,
        run_id: UUID | None = None,
    ) -> CognitiveContextBundle: ...


async def safe_cognitive_context_text(
    advisor: CognitiveAdvisorProtocol | None,
    *,
    tenant_id: UUID,
    user_id: UUID,
    scene: str,
    current_request: str,
    conversation_id: str | None = None,
    run_id: UUID | None = None,
    timeout_seconds: float = 0.8,
) -> str:
    if advisor is None:
        return ""
    try:
        bundle = await asyncio.wait_for(
            advisor.advise(
                tenant_id=tenant_id,
                user_id=user_id,
                scene=scene,
                current_request=current_request,
                conversation_id=conversation_id,
                run_id=run_id,
            ),
            timeout=timeout_seconds,
        )
    except Exception:
        return ""
    return render_cognitive_context(bundle)
```

- [ ] **Step 4: Wire RunService best-effort advice**

Modify `RunService.__init__` to accept `cognitive_advisor: CognitiveAdvisorProtocol | None = None`.

Before mode execution, call `safe_cognitive_context_text` with:

- `scene="task_execution"` for Web/admin runs.
- `scene="voice_chat"` when routing decision or request source later marks a voice session.
- `current_request` equal to the submitted user request.

Store only routing metadata in `routing_decision["cognition"]`:

```python
{
    "status": "available" if cognitive_context else "empty",
    "scene": scene,
    "injected": bool(cognitive_context),
}
```

Do not store the full cognitive context in run metadata if it contains user-sensitive relationship or belief content. Pass the rendered context to prompt construction through `ContextBuildInput.cognitive_context` when that path is available; otherwise append a bounded cognitive block beside the Hermes context in the runtime-specific prompt bridge.

- [ ] **Step 5: Add outcome hook stub**

Add `CognitiveOutcomeIngestProtocol` in `runtime.py`:

```python
class CognitiveOutcomeIngestProtocol(Protocol):
    async def ingest_run_outcome(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        run_id: UUID,
        status: str,
        request: str,
        routing_decision: dict[str, object],
    ) -> None: ...
```

Modify terminal run completion handling in `RunService` to call the hook best-effort after Hermes outcome recording. It must swallow exceptions and log them, matching Hermes failure isolation.

- [ ] **Step 6: Run focused runtime tests**

Run: `pytest tests/unit/runtime/test_cognitive_context.py tests/unit/runs/test_conversation_mode.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/agent_hub/cognition/runtime.py src/agent_hub/runs/service.py tests/unit/runtime/test_cognitive_context.py tests/unit/runs/test_conversation_mode.py
git commit -m "feat: add best-effort cognitive runtime context"
```

---

### Task 9: Admin API

**Files:**
- Create: `src/agent_hub/api/routers/cognition.py`
- Modify: `src/agent_hub/app.py`
- Modify: `src/agent_hub/auth/models.py`
- Test: `tests/api/test_cognition_api.py`
- Test: `tests/unit/auth/test_rbac.py`

**Interfaces:**
- Consumes: cognition services and repository.
- Produces API routes under `/api/v1/admin/cognition`.
- Produces endpoints:
  - `GET /api/v1/admin/cognition/episodes`
  - `POST /api/v1/admin/cognition/episodes`
  - `GET /api/v1/admin/cognition/experiences`
  - `POST /api/v1/admin/cognition/experiences/{experience_id}/outcome`
  - `GET /api/v1/admin/cognition/reflections`
  - `GET /api/v1/admin/cognition/beliefs`
  - `GET /api/v1/admin/cognition/relationship`
  - `GET /api/v1/admin/cognition/world-state`
  - `POST /api/v1/admin/cognition/router-preview`

- [ ] **Step 1: Write failing API tests**

```python
from datetime import UTC, datetime


def test_cognition_episode_ingest_requires_permission(api, headers):
    response = api.post(
        "/api/v1/admin/cognition/episodes",
        headers=headers(),
        json={
            "source": "voice",
            "conversation_id": "conv-api-cognition",
            "started_at": datetime(2026, 9, 10, 12, 0, tzinfo=UTC).isoformat(),
            "summary": "User corrected the assistant about long voice replies.",
            "signals": ["user_corrected"],
            "outcome": "neutral",
            "evidence_refs": [{"kind": "conversation", "ref_id": "conv-api-cognition", "summary": "correction"}],
        },
    )

    assert response.status_code == 200
    assert response.json()["episode_stored"] is True
    assert response.json()["experience_created"] is True


def test_cognition_router_preview_returns_bounded_context(api, headers):
    response = api.post(
        "/api/v1/admin/cognition/router-preview",
        headers=headers(),
        json={"scene": "voice_chat", "current_request": "deployment debugging", "limit": 4},
    )

    assert response.status_code == 200
    assert "experience_context" in response.json()
```

- [ ] **Step 2: Run and confirm failure**

Run: `pytest tests/api/test_cognition_api.py -v`

Expected: FAIL with `404` for `/api/v1/admin/cognition/episodes`.

- [ ] **Step 3: Add RBAC permissions**

Modify `src/agent_hub/auth/models.py` so:

- `super_admin` retains `*`.
- `admin` includes `cognition:*`.
- `operator` includes `cognition:read` and `cognition:write` only if existing operator role already has comparable `memory:write`; otherwise operator gets `cognition:read`.
- `viewer` gets no cognition write permission.

Add focused assertions to `tests/unit/auth/test_rbac.py`.

- [ ] **Step 4: Implement router dependency**

In `src/agent_hub/api/routers/cognition.py`, create an `APIRouter(prefix="/api/v1/admin/cognition", tags=["admin", "cognition"])`. Use `current_principal` and `Authorizer().require(...)` in the same style as admin routes. Build `AdminResourceCognitionRepository` from app state session factory, `principal.tenant_id`, and `principal.user_id`.

- [ ] **Step 5: Implement endpoint behavior**

`POST /episodes` must validate `CognitiveEpisode` using tenant/user from principal, call `ExperienceStore.record_episode`, and return `EpisodeIngestResult`.

`POST /router-preview` must call `MemoryExperienceRouter.build_context_bundle` and return the bundle.

List endpoints must read records by `record_type`, validate them into the corresponding Pydantic models, and return arrays.

- [ ] **Step 6: Mount the router**

Modify `src/agent_hub/app.py`:

```python
from agent_hub.api.routers import admin, auth, cognition, config, runs, system, users
```

and add:

```python
application.router.routes.extend(cognition.router.routes)
```

near the other admin routers.

- [ ] **Step 7: Run API and RBAC tests**

Run: `pytest tests/api/test_cognition_api.py tests/unit/auth/test_rbac.py -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/agent_hub/api/routers/cognition.py src/agent_hub/app.py src/agent_hub/auth/models.py tests/api/test_cognition_api.py tests/unit/auth/test_rbac.py
git commit -m "feat: expose cognition admin api"
```

---

### Task 10: Web Debug Surface

**Files:**
- Modify: `web/src/api/client.ts`
- Modify: `web/src/app/router.tsx`
- Modify: `web/src/app/navSections.ts`
- Create: `web/src/pages/CognitionPage.tsx`
- Create: `web/src/pages/CognitionPage.test.tsx`

**Interfaces:**
- Consumes: `/api/v1/admin/cognition/*` endpoints.
- Produces: `api.cognitionEpisodes()`, `api.cognitionExperiences()`, `api.cognitionRouterPreview(payload)`.
- Produces: `/cognition` page with tabs for Episodes, Experiences, Reflections, Beliefs, Relationship, World State, and Router Preview.

- [ ] **Step 1: Write failing frontend API tests**

Add schemas to `client.ts` tests if a dedicated API client test file exists; otherwise add coverage in `CognitionPage.test.tsx` with mocked `fetch`.

```tsx
it("loads cognition page and renders sparse learning records", async () => {
  const requests: Array<{ path: string; method: string }> = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const path = String(input);
    requests.push({ path, method: init?.method ?? "GET" });
    if (path === "/api/v1/admin/me") return jsonResponse({ username: "admin", role: "super_admin", permissions: ["*"] });
    if (path === "/api/v1/admin/cognition/episodes") return jsonResponse([]);
    if (path === "/api/v1/admin/cognition/experiences") {
      return jsonResponse([{ id: "exp-1", kind: "voice_interaction", statement: "Use shorter voice replies.", confidence: 0.82, status: "active" }]);
    }
    if (path === "/api/v1/admin/cognition/reflections") return jsonResponse([]);
    if (path === "/api/v1/admin/cognition/beliefs") return jsonResponse([]);
    if (path === "/api/v1/admin/cognition/relationship") return jsonResponse(null);
    if (path === "/api/v1/admin/cognition/world-state") return jsonResponse([]);
    return jsonResponse({});
  });

  render(<TestApp initialEntries={["/cognition"]} />);

  expect(await screen.findByRole("heading", { name: "认知成长" })).toBeInTheDocument();
  expect(await screen.findByText("Use shorter voice replies.")).toBeInTheDocument();
  expect(requests.some((request) => request.path === "/api/v1/admin/cognition/experiences")).toBe(true);
});
```

- [ ] **Step 2: Run and confirm failure**

Run: `npm test -- --run web/src/pages/CognitionPage.test.tsx`

Expected: FAIL because `CognitionPage.tsx` or `/cognition` route does not exist.

- [ ] **Step 3: Add client schemas and methods**

In `web/src/api/client.ts`, add Zod schemas for:

- `CognitionEpisodeSchema`
- `CognitionExperienceSchema`
- `CognitionReflectionSchema`
- `CognitionBeliefSchema`
- `CognitionRelationshipSchema`
- `CognitionWorldStateSchema`
- `CognitiveContextBundleSchema`

Add API methods:

```ts
cognitionEpisodes(): Promise<CognitionEpisode[]> {
  return request("/api/v1/admin/cognition/episodes", { method: "GET" }, z.array(CognitionEpisodeSchema));
},
cognitionExperiences(): Promise<CognitionExperience[]> {
  return request("/api/v1/admin/cognition/experiences", { method: "GET" }, z.array(CognitionExperienceSchema));
},
cognitionRouterPreview(payload: { scene: string; current_request: string; limit?: number }): Promise<CognitiveContextBundle> {
  return request("/api/v1/admin/cognition/router-preview", {
    method: "POST",
    body: JSON.stringify(payload),
  }, CognitiveContextBundleSchema);
},
```

- [ ] **Step 4: Add page and route**

`CognitionPage.tsx` should be an operational console, not a landing page. First screen must show dense data:

- top metrics: candidate experiences, active experiences, contradicted beliefs, active world items.
- tabs or segmented controls for record types.
- table columns: type, statement/summary, confidence, evidence count, status, last verified, updated.
- router preview form with `scene`, `current_request`, and `limit`.
- preview output showing selected context groups and reasons.

Add `/cognition` route in `web/src/app/router.tsx` and navigation entry in `web/src/app/navSections.ts`.

- [ ] **Step 5: Run focused frontend tests**

Run: `npm test -- --run web/src/pages/CognitionPage.test.tsx`

Expected: PASS.

- [ ] **Step 6: Run broader frontend gate**

Run: `npm test -- --run`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add web/src/api/client.ts web/src/app/router.tsx web/src/app/navSections.ts web/src/pages/CognitionPage.tsx web/src/pages/CognitionPage.test.tsx
git commit -m "feat: add cognition debug console"
```

---

### Task 11: Security, Integration, And Final Verification

**Files:**
- Create: `tests/security/test_cognition_safety.py`
- Modify: `HANDOFF.md`

**Interfaces:**
- Consumes all previous tasks.
- Produces verified behavior for sparse learning, safety rejection, protected self-model boundaries, tenant/user isolation, and frontend visibility.

- [ ] **Step 1: Write safety tests**

```python
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from agent_hub.cognition.experience_store import ExperienceStore
from agent_hub.cognition.repository import InMemoryCognitionRepository
from agent_hub.cognition.types import CognitiveEpisode, CognitiveSource, EvidenceRef


@pytest.mark.asyncio
async def test_cognition_rejects_secret_like_episode() -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    store = ExperienceStore(InMemoryCognitionRepository(tenant_id=tenant_id, user_id=user_id))
    episode = CognitiveEpisode(
        tenant_id=tenant_id,
        user_id=user_id,
        source=CognitiveSource.WEB,
        started_at=datetime(2026, 9, 10, 14, 0, tzinfo=UTC),
        summary="User pasted password=abc123 and asked the agent to remember it.",
        evidence_refs=(EvidenceRef(kind="conversation", ref_id="conv-secret", summary="secret paste"),),
    )

    result = await store.record_episode(episode)

    assert result.experience_created is False
    assert result.rejection_reason == "unsafe_content"
```

- [ ] **Step 2: Run security tests**

Run: `pytest tests/security/test_cognition_safety.py -v`

Expected: PASS.

- [ ] **Step 3: Run backend focused suite**

Run:

```bash
pytest tests/unit/cognition tests/api/test_cognition_api.py tests/integration/cognition/test_cognition_persistence.py tests/security/test_cognition_safety.py -v
```

Expected: PASS.

- [ ] **Step 4: Run frontend focused suite**

Run:

```bash
npm test -- --run web/src/pages/CognitionPage.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Run project formatting and static checks available in this repo**

Run:

```bash
ruff check src tests
git diff --check
```

Expected: PASS.

If mypy is already passing on the current branch before this work, run:

```bash
mypy src
```

Expected: PASS. If baseline mypy is already failing before cognition changes, record the baseline failure in `HANDOFF.md` and ensure no cognition files are responsible.

- [ ] **Step 6: Update handoff**

Update `HANDOFF.md` with:

- implemented cognitive slices.
- verification commands and results.
- unresolved risks.
- next recommended work: robot protocol, Pi runtime, first-boot provisioning, and OTA plan.

- [ ] **Step 7: Commit**

```bash
git add tests/security/test_cognition_safety.py HANDOFF.md
git commit -m "test: verify cognition safety boundaries"
```

---

## Self-Review

Spec coverage:

- Sparse high-signal learning is covered by Tasks 1, 3, 4, 6, and 10.
- Episode, Experience, Reflection, Belief, Relationship, World State, and Self Model are covered by Tasks 1, 3, 4, and 5.
- Confidence, evidence, contradiction, usage, success/failure, last verification, version, and status are covered by Tasks 1, 3, and 5.
- Dynamic bounded retrieval is covered by Task 6.
- Hermes, Memory, Evolution, and Skill integration is covered by Task 7.
- Runtime influence and non-blocking outcome ingestion are covered by Task 8.
- Admin API and Web debug visibility are covered by Tasks 9 and 10.
- Protected persona, SOUL, safety, permissions, and hardware-control boundaries are covered by Tasks 5, 7, and 11.
- Tenant/user isolation is covered by Tasks 2, 9, and 11.

Placeholder scan:

- The plan contains no unfinished placeholder sections.
- Each implementation task has concrete files, interfaces, tests, commands, and commit steps.

Type consistency:

- Domain names are anchored in Task 1 and reused by later tasks.
- Repository names are anchored in Task 2 and reused by service, router, and API tasks.
- `CognitiveContextBundle` is produced by the router in Task 6 and consumed by the API and frontend in Tasks 8 and 9.

## Execution Mode

Use Subagent-Driven execution inside the current Codex task only. Do not create new top-level Codex conversations or visible sidebar tasks. Dispatch fresh subagents per implementation task or per disjoint write scope, then review and integrate their changes in this same session.
