from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from agent_hub.cognition.evidence import contains_evidence, merge_evidence, validated_update
from agent_hub.cognition.repository import CognitionRepository
from agent_hub.cognition.types import (
    BeliefRecord,
    BeliefStatus,
    CognitiveRecordStatus,
    EvidenceRef,
    ExperienceKind,
    ExperienceRecord,
    ProtectedChangeProposal,
    RelationshipState,
    WorldStateItem,
)

BELIEF_RECORD_TYPE = "belief"
RELATIONSHIP_RECORD_TYPE = "relationship"
WORLD_STATE_RECORD_TYPE = "world_state"
PROTECTED_CHANGE_PROPOSAL_RECORD_TYPE = "protected_change_proposal"
SELF_MODEL_RECORD_TYPE = "self_model"


class BeliefService:
    def __init__(self, repository: CognitionRepository) -> None:
        self._repository = repository

    async def upsert_belief(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        subject: str,
        predicate: str,
        object: str,
        scope: str,
        evidence: EvidenceRef,
    ) -> BeliefRecord:
        merge_evidence((), (evidence,))
        existing = await self._find_matching_belief(
            subject=subject,
            predicate=predicate,
            object=object,
            scope=scope,
        )
        if existing is None:
            belief = BeliefRecord(
                tenant_id=tenant_id,
                user_id=user_id,
                subject=subject,
                predicate=predicate,
                object=object,
                scope=scope,
                confidence=0.45,
                evidence_refs=(evidence,),
                status=BeliefStatus.CANDIDATE,
            )
            return await self._persist_belief(belief)

        if contains_evidence((*existing.evidence_refs, *existing.contradictions), evidence):
            return existing
        now = _advanced_now(existing.updated_at)
        confidence = _clamp_score(existing.confidence + 0.07)
        status = BeliefStatus.ACTIVE if confidence >= 0.75 else _candidate_or_uncertain(existing.status)
        updated = validated_update(
            existing,
            update={
                "confidence": confidence,
                "evidence_refs": merge_evidence(existing.evidence_refs, (evidence,)),
                "verification_count": existing.verification_count + 1,
                "last_verified_at": now,
                "status": status,
                "version": existing.version + 1,
                "updated_at": now,
            }
        )
        return await self._persist_belief(updated)

    async def apply_contradiction(self, belief_id: UUID, evidence: EvidenceRef) -> BeliefRecord:
        merge_evidence((), (evidence,))
        payload = await self._repository.get(BELIEF_RECORD_TYPE, str(belief_id))
        if payload is None:
            raise LookupError(f"belief {belief_id} was not found")

        belief = _belief_from_payload(payload)
        if contains_evidence(belief.contradictions, evidence):
            return belief
        now = _advanced_now(belief.updated_at)
        confidence = _clamp_score(belief.confidence - 0.15)
        status = BeliefStatus.CONTRADICTED if confidence < 0.35 else BeliefStatus.UNCERTAIN
        updated = validated_update(
            belief,
            update={
                "confidence": confidence,
                "contradictions": merge_evidence(belief.contradictions, (evidence,)),
                "status": status,
                "version": belief.version + 1,
                "updated_at": now,
            }
        )
        return await self._persist_belief(updated)

    async def _find_matching_belief(
        self,
        *,
        subject: str,
        predicate: str,
        object: str,
        scope: str,
    ) -> BeliefRecord | None:
        for payload in await self._repository.list(BELIEF_RECORD_TYPE):
            belief = _belief_from_payload(payload)
            if (
                belief.subject == subject
                and belief.predicate == predicate
                and belief.object == object
                and belief.scope == scope
            ):
                return belief
        return None

    async def _persist_belief(self, belief: BeliefRecord) -> BeliefRecord:
        stored = await self._repository.upsert(
            BELIEF_RECORD_TYPE,
            str(belief.id),
            belief.model_dump(mode="json"),
        )
        return _belief_from_payload(stored)


class RelationshipService:
    def __init__(self, repository: CognitionRepository) -> None:
        self._repository = repository

    async def update_from_experience(self, experience: ExperienceRecord) -> RelationshipState:
        existing = await self._load_relationship(experience.tenant_id, experience.user_id)
        evidence_refs = merge_evidence((), experience.evidence_refs, limit=32)
        now = _now()
        if existing is None:
            relationship = RelationshipState(
                tenant_id=experience.tenant_id,
                user_id=experience.user_id,
                evidence_refs=evidence_refs,
                preferred_depth=_preferred_depth_from_experience(experience, current="balanced"),
                familiarity=_familiarity_delta(0.0, experience),
                trust=_trust_delta(0.5, experience),
                last_updated_at=now,
            )
            return await self._persist_relationship(relationship)

        now = _advanced_now(existing.last_updated_at)
        updated = validated_update(
            existing,
            update={
                "familiarity": _familiarity_delta(existing.familiarity, experience),
                "trust": _trust_delta(existing.trust, experience),
                "preferred_depth": _preferred_depth_from_experience(
                    experience,
                    current=existing.preferred_depth,
                ),
                "evidence_refs": merge_evidence(existing.evidence_refs, evidence_refs, limit=32),
                "version": existing.version + 1,
                "last_updated_at": now,
            }
        )
        return await self._persist_relationship(updated)

    async def _load_relationship(self, tenant_id: UUID, user_id: UUID) -> RelationshipState | None:
        payload = await self._repository.get(RELATIONSHIP_RECORD_TYPE, _relationship_id(tenant_id, user_id))
        if payload is None:
            return None
        return _relationship_from_payload(payload)

    async def _persist_relationship(self, relationship: RelationshipState) -> RelationshipState:
        stored = await self._repository.upsert(
            RELATIONSHIP_RECORD_TYPE,
            _relationship_id(relationship.tenant_id, relationship.user_id),
            relationship.model_dump(mode="json"),
        )
        return _relationship_from_payload(stored)


class WorldStateService:
    def __init__(self, repository: CognitionRepository) -> None:
        self._repository = repository

    async def upsert_item(self, item: WorldStateItem) -> WorldStateItem:
        if not item.evidence_refs:
            raise ValueError("world state item requires evidence")
        stored = await self._repository.upsert(
            WORLD_STATE_RECORD_TYPE,
            str(item.id),
            item.model_dump(mode="json"),
        )
        return _world_state_from_payload(stored)

    async def mark_status(self, item_id: UUID, status: str, evidence: EvidenceRef) -> WorldStateItem:
        payload = await self._repository.get(WORLD_STATE_RECORD_TYPE, str(item_id))
        if payload is None:
            raise LookupError(f"world state item {item_id} was not found")

        item = _world_state_from_payload(payload)
        now = _advanced_now(item.updated_at)
        updated = WorldStateItem.model_validate(
            {
                **item.model_dump(mode="json"),
                "status": status,
                "evidence_refs": merge_evidence(item.evidence_refs, (evidence,)),
                "last_verified_at": now,
                "version": item.version + 1,
                "updated_at": now,
            }
        )
        return await self.upsert_item(updated)


class SelfModelService:
    def __init__(self, repository: CognitionRepository) -> None:
        self._repository = repository

    async def propose_change(
        self,
        *,
        target: str,
        proposed_change: str,
        evidence_refs: tuple[EvidenceRef, ...],
        confidence: float,
    ) -> ProtectedChangeProposal:
        proposal = ProtectedChangeProposal(
            target=target,
            proposed_change=proposed_change,
            evidence_refs=evidence_refs,
            confidence=confidence,
            requires_approval=True,
            status=CognitiveRecordStatus.CANDIDATE,
        )
        stored = await self._repository.upsert(
            PROTECTED_CHANGE_PROPOSAL_RECORD_TYPE,
            str(proposal.id),
            proposal.model_dump(mode="json"),
        )
        return _proposal_from_payload(stored)


def _belief_from_payload(payload: dict[str, object]) -> BeliefRecord:
    return BeliefRecord.model_validate(_model_payload(payload))


def _relationship_from_payload(payload: dict[str, object]) -> RelationshipState:
    values = _model_payload(payload)
    values.pop("id", None)
    return RelationshipState.model_validate(values)


def _world_state_from_payload(payload: dict[str, object]) -> WorldStateItem:
    return WorldStateItem.model_validate(_model_payload(payload))


def _proposal_from_payload(payload: dict[str, object]) -> ProtectedChangeProposal:
    values = _model_payload(payload)
    values.pop("tenant_id", None)
    values.pop("user_id", None)
    return ProtectedChangeProposal.model_validate(values)


def _model_payload(payload: dict[str, object]) -> dict[str, object]:
    values = dict(payload)
    values.pop("record_type", None)
    return values


def _relationship_id(tenant_id: UUID, user_id: UUID) -> str:
    return f"{tenant_id}:{user_id}"


def _preferred_depth_from_experience(experience: ExperienceRecord, *, current: str) -> str:
    action = experience.recommended_action.lower()
    if experience.kind is ExperienceKind.VOICE_INTERACTION and (
        "short" in action or "concise" in action
    ) and ("spoken" in action or "voice" in action or "replies" in action):
        return "concise"
    return current


def _familiarity_delta(current: float, experience: ExperienceRecord) -> float:
    if experience.success_count > 0:
        return _clamp_score(current + 0.03)
    return current


def _trust_delta(current: float, experience: ExperienceRecord) -> float:
    if experience.failure_count > 0:
        return _clamp_score(current - 0.04)
    if experience.success_count > 0:
        return _clamp_score(current + 0.03)
    return current


def _candidate_or_uncertain(status: BeliefStatus) -> BeliefStatus:
    return BeliefStatus.UNCERTAIN if status is BeliefStatus.UNCERTAIN else BeliefStatus.CANDIDATE


def _clamp_score(value: float) -> float:
    return min(1.0, max(0.0, round(value, 10)))


def _now() -> datetime:
    return datetime.now().astimezone()


def _advanced_now(previous: datetime) -> datetime:
    now = _now()
    if now <= previous:
        return previous + timedelta(microseconds=1)
    return now
