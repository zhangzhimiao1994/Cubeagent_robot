from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from agent_hub.cognition.repository import InMemoryCognitionRepository
from agent_hub.cognition.state import (
    BeliefService,
    RelationshipService,
    SelfModelService,
    WorldStateService,
)
from agent_hub.cognition.types import (
    BeliefStatus,
    CognitiveRecordStatus,
    EvidenceRef,
    ExperienceKind,
    ExperienceRecord,
    ProtectedChangeProposal,
    WorldEntityType,
    WorldStateItem,
)


def _repository() -> tuple[UUID, UUID, InMemoryCognitionRepository]:
    tenant_id = uuid4()
    user_id = uuid4()
    return tenant_id, user_id, InMemoryCognitionRepository(tenant_id=tenant_id, user_id=user_id)


def _evidence(ref_id: str = "exp-1", summary: str = "user accepted short voice answer") -> EvidenceRef:
    return EvidenceRef(kind="experience", ref_id=ref_id, summary=summary)


def _experience(
    tenant_id: UUID,
    user_id: UUID,
    *,
    kind: ExperienceKind = ExperienceKind.VOICE_INTERACTION,
    success_count: int = 0,
    failure_count: int = 0,
    recommended_action: str = "Use short, concise spoken replies during debugging.",
) -> ExperienceRecord:
    return ExperienceRecord(
        tenant_id=tenant_id,
        user_id=user_id,
        kind=kind,
        statement="User prefers concise spoken debugging replies.",
        applicability="voice debugging",
        recommended_action=recommended_action,
        evidence_refs=(_evidence(),),
        success_count=success_count,
        failure_count=failure_count,
    )


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


@pytest.mark.asyncio
async def test_belief_upsert_reinforces_matching_payload_until_active() -> None:
    tenant_id, user_id, repository = _repository()
    service = BeliefService(repository)

    first = await service.upsert_belief(
        tenant_id=tenant_id,
        user_id=user_id,
        subject="user",
        predicate="prefers",
        object="short voice replies during debugging",
        scope="voice_debugging",
        evidence=_evidence("exp-1"),
    )
    reinforced = first
    for index in range(2, 7):
        reinforced = await service.upsert_belief(
            tenant_id=tenant_id,
            user_id=user_id,
            subject="user",
            predicate="prefers",
            object="short voice replies during debugging",
            scope="voice_debugging",
            evidence=_evidence(f"exp-{index}"),
        )

    beliefs = await repository.list("belief")

    assert len(beliefs) == 1
    assert reinforced.id == first.id
    assert reinforced.confidence == 0.8
    assert reinforced.verification_count == 5
    assert reinforced.status is BeliefStatus.ACTIVE
    assert reinforced.version == 6
    assert reinforced.last_verified_at is not None
    assert reinforced.updated_at > first.updated_at
    assert [evidence.ref_id for evidence in reinforced.evidence_refs] == [
        "exp-1",
        "exp-2",
        "exp-3",
        "exp-4",
        "exp-5",
        "exp-6",
    ]


@pytest.mark.asyncio
async def test_belief_contradiction_marks_uncertain_or_contradicted_by_confidence() -> None:
    tenant_id, user_id, repository = _repository()
    service = BeliefService(repository)
    await service.upsert_belief(
        tenant_id=tenant_id,
        user_id=user_id,
        subject="user",
        predicate="prefers",
        object="short voice replies during debugging",
        scope="voice_debugging",
        evidence=_evidence("exp-1"),
    )
    belief = await service.upsert_belief(
        tenant_id=tenant_id,
        user_id=user_id,
        subject="user",
        predicate="prefers",
        object="short voice replies during debugging",
        scope="voice_debugging",
        evidence=_evidence("exp-2"),
    )

    uncertain = await service.apply_contradiction(belief.id, _evidence("exp-3", "one mismatch"))
    contradicted = await service.apply_contradiction(belief.id, _evidence("exp-4", "second mismatch"))

    assert uncertain.status is BeliefStatus.UNCERTAIN
    assert uncertain.confidence == 0.37
    assert contradicted.status is BeliefStatus.CONTRADICTED
    assert contradicted.confidence == 0.22
    assert contradicted.version == 4


@pytest.mark.asyncio
async def test_belief_contradiction_missing_belief_raises_lookup_error() -> None:
    _, _, repository = _repository()
    service = BeliefService(repository)

    with pytest.raises(LookupError, match="belief"):
        await service.apply_contradiction(uuid4(), _evidence())


@pytest.mark.asyncio
async def test_relationship_update_from_voice_experience_tracks_preferred_depth_and_scores() -> None:
    tenant_id, user_id, repository = _repository()
    service = RelationshipService(repository)
    experience = _experience(tenant_id, user_id, success_count=1)

    first = await service.update_from_experience(experience)
    second = await service.update_from_experience(
        _experience(tenant_id, user_id, success_count=1, recommended_action="Keep spoken replies short.")
    )
    relationships = await repository.list("relationship")

    assert len(relationships) == 1
    assert first.preferred_depth == "concise"
    assert second.preferred_depth == "concise"
    assert second.familiarity == 0.06
    assert second.trust == 0.56
    assert second.version == 2
    assert second.last_updated_at > first.last_updated_at
    assert len(second.evidence_refs) == 2


@pytest.mark.asyncio
async def test_relationship_failed_experience_lowers_trust() -> None:
    tenant_id, user_id, repository = _repository()
    service = RelationshipService(repository)

    updated = await service.update_from_experience(_experience(tenant_id, user_id, failure_count=1))

    assert updated.familiarity == 0.0
    assert updated.trust == 0.46
    assert updated.evidence_refs == (_evidence(),)


@pytest.mark.asyncio
async def test_world_state_upsert_requires_evidence_and_mark_status_persists_update() -> None:
    tenant_id, user_id, repository = _repository()
    service = WorldStateService(repository)
    item = WorldStateItem(
        tenant_id=tenant_id,
        user_id=user_id,
        entity_type=WorldEntityType.TASK,
        name="Deploy cognitive layer",
        state="Needs focused verification",
        evidence_refs=(_evidence("exp-1"),),
    )

    stored = await service.upsert_item(item)
    completed = await service.mark_status(stored.id, "completed", _evidence("exp-2", "verified done"))
    persisted = await repository.get("world_state", str(item.id))

    assert stored == item
    assert completed.status == "completed"
    assert completed.evidence_refs == (_evidence("exp-1"), _evidence("exp-2", "verified done"))
    assert completed.version == 2
    assert completed.last_verified_at is not None
    assert completed.updated_at > stored.updated_at
    assert persisted is not None
    assert persisted["status"] == "completed"


@pytest.mark.asyncio
async def test_world_state_rejects_records_without_evidence() -> None:
    tenant_id, user_id, repository = _repository()
    service = WorldStateService(repository)

    with pytest.raises(ValueError, match="evidence"):
        await service.upsert_item(
            WorldStateItem.model_construct(
                id=uuid4(),
                tenant_id=tenant_id,
                user_id=user_id,
                entity_type=WorldEntityType.TASK,
                name="Deploy cognitive layer",
                state="Needs focused verification",
                status="active",
                evidence_refs=(),
                confidence=0.5,
                version=1,
            )
        )


@pytest.mark.asyncio
async def test_world_state_mark_status_missing_item_raises_lookup_error() -> None:
    _, _, repository = _repository()
    service = WorldStateService(repository)

    with pytest.raises(LookupError, match="world state"):
        await service.mark_status(uuid4(), "completed", _evidence())


@pytest.mark.asyncio
async def test_world_state_mark_status_rejects_invalid_status_without_persisting() -> None:
    tenant_id, user_id, repository = _repository()
    service = WorldStateService(repository)
    item = WorldStateItem(
        tenant_id=tenant_id,
        user_id=user_id,
        entity_type=WorldEntityType.TASK,
        name="Deploy cognitive layer",
        state="Needs focused verification",
        evidence_refs=(_evidence("exp-1"),),
    )
    await service.upsert_item(item)

    with pytest.raises(ValidationError, match="status"):
        await service.mark_status(item.id, "blocked", _evidence("exp-2", "invalid status"))

    persisted = await repository.get("world_state", str(item.id))

    assert persisted is not None
    assert persisted["status"] == "active"
    assert persisted["version"] == 1
    assert persisted["evidence_refs"] == [_evidence("exp-1").model_dump(mode="json")]


@pytest.mark.asyncio
async def test_self_model_change_creates_protected_proposal_without_mutating_self_model() -> None:
    _, _, repository = _repository()
    service = SelfModelService(repository)
    evidence = _evidence("reflection-1", "candidate improvement from reflection")

    proposal = await service.propose_change(
        target="persona",
        proposed_change="Use shorter spoken debugging updates by default.",
        evidence_refs=(evidence,),
        confidence=0.64,
    )

    proposals = await repository.list("protected_change_proposal")

    assert isinstance(proposal, ProtectedChangeProposal)
    assert proposal.requires_approval is True
    assert proposal.status is CognitiveRecordStatus.CANDIDATE
    assert proposal.evidence_refs == (evidence,)
    assert proposal.confidence == 0.64
    assert len(proposals) == 1
    assert proposals[0]["requires_approval"] is True
    assert await repository.list("self_model") == ()
