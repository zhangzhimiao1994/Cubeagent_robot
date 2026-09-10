from datetime import UTC, datetime
from uuid import uuid4

import pytest

from agent_hub.cognition.experience_store import ExperienceStore
from agent_hub.cognition.repository import InMemoryCognitionRepository
from agent_hub.cognition.router import MemoryExperienceRouter
from agent_hub.cognition.state import (
    BeliefService,
    RelationshipService,
    SelfModelService,
    WorldStateService,
)
from agent_hub.cognition.types import (
    BeliefRecord,
    CognitiveEpisode,
    EvidenceRef,
    ExperienceRecord,
    RelationshipState,
    WorldStateItem,
)


def evidence(index=0, **changes):
    return EvidenceRef(kind="episode", ref_id=f"ep-{index}", summary="accepted", **changes)


def setup_store(**changes):
    tenant, user = uuid4(), uuid4()
    repo = InMemoryCognitionRepository(tenant_id=tenant, user_id=user)
    record = ExperienceRecord(
        tenant_id=tenant,
        user_id=user,
        kind="strategy",
        statement="deployment checks",
        applicability="deployment",
        evidence_refs=(evidence(),),
        **changes,
    )
    return repo, record


@pytest.mark.parametrize("succeeded", [True, False])
@pytest.mark.parametrize("field", ["summary", "ref_id", "kind"])
async def test_outcome_rejects_unsafe_evidence_without_writing(succeeded, field):
    repo, record = setup_store()
    await repo.upsert("experience", str(record.id), record.model_dump(mode="json"))
    before = await repo.get("experience", str(record.id))
    unsafe = EvidenceRef.model_validate({**evidence(1).model_dump(), field: "password=private"})
    with pytest.raises(ValueError, match="unsafe"):
        await ExperienceStore(repo).record_outcome(record.id, succeeded, unsafe)
    assert await repo.get("experience", str(record.id)) == before


@pytest.mark.parametrize("succeeded", [True, False])
async def test_outcome_evidence_stays_valid_at_capacity(succeeded):
    repo, record = setup_store()
    await repo.upsert("experience", str(record.id), record.model_dump(mode="json"))
    for index in range(1, 22):
        updated = await ExperienceStore(repo).record_outcome(record.id, succeeded, evidence(index))
        assert len(updated.evidence_refs) <= 16
        assert len(updated.contradictions) <= 16
        payload = await repo.get("experience", str(record.id))
        payload.pop("record_type", None)
        ExperienceRecord.model_validate(payload)


async def test_belief_retries_do_not_raise_confidence_or_recount_contradictions():
    repo, record = setup_store()
    service = BeliefService(repo)
    args = {
        "tenant_id": record.tenant_id,
        "user_id": record.user_id,
        "subject": "user",
        "predicate": "prefers",
        "object": "concise",
        "scope": "voice",
    }
    first = await service.upsert_belief(**args, evidence=evidence())
    for _ in range(8):
        repeated = await service.upsert_belief(
            **args,
            evidence=EvidenceRef(kind="episode", ref_id="ep-0", summary="same source rephrased"),
        )
    assert repeated == first
    contradicted = await service.apply_contradiction(first.id, evidence(1))
    assert await service.apply_contradiction(first.id, evidence(1)) == contradicted


async def test_belief_evidence_and_contradictions_remain_valid_at_capacity():
    repo, record = setup_store()
    service = BeliefService(repo)
    args = {
        "tenant_id": record.tenant_id,
        "user_id": record.user_id,
        "subject": "user",
        "predicate": "prefers",
        "object": "concise",
        "scope": "voice",
    }
    for index in range(22):
        belief = await service.upsert_belief(**args, evidence=evidence(index))
        assert len(belief.evidence_refs) <= 16
    for index in range(22, 44):
        belief = await service.apply_contradiction(belief.id, evidence(index))
        assert len(belief.contradictions) <= 16
    payload = await repo.get("belief", str(belief.id))
    payload.pop("record_type", None)
    BeliefRecord.model_validate(payload)


async def test_relationship_evidence_remains_valid_at_capacity():
    repo, record = setup_store()
    service = RelationshipService(repo)
    for index in range(36):
        experience = ExperienceRecord.model_validate(
            {**record.model_dump(), "evidence_refs": (evidence(index),)}
        )
        state = await service.update_from_experience(experience)
        assert len(state.evidence_refs) <= 32
    payload = (await repo.list("relationship"))[0]
    payload.pop("record_type", None)
    payload.pop("id", None)
    RelationshipState.model_validate(payload)


async def test_long_episode_promotes_to_bounded_experience():
    repo, record = setup_store()
    episode = CognitiveEpisode(
        tenant_id=record.tenant_id,
        user_id=record.user_id,
        source="voice",
        started_at=datetime.now(UTC),
        summary="voice correction " * 110,
        signals=("user_corrected",),
        evidence_refs=(evidence(),),
    )
    result = await ExperienceStore(repo).record_episode(episode)
    assert result.experience_created
    assert len(result.experience.statement) <= 1000
    assert len(await repo.list("reflection")) == 1


async def test_protected_proposal_accepts_sql_repository_scope_metadata():
    class SQLShapedRepository(InMemoryCognitionRepository):
        async def upsert(self, record_type, record_id, payload):
            return await super().upsert(
                record_type,
                record_id,
                {
                    **payload,
                    "tenant_id": str(self._tenant_id),
                    "user_id": str(self._user_id),
                },
            )

    repo = SQLShapedRepository(tenant_id=uuid4(), user_id=uuid4())
    result = await SelfModelService(repo).propose_change(
        target="identity",
        proposed_change="bounded change",
        evidence_refs=(evidence(),),
        confidence=0.5,
    )
    assert result.requires_approval
    assert len(await repo.list("protected_change_proposal")) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"confidence": 0},
        {"confidence": 0.9, "contradictions": (evidence(1),)},
        {"statement": "garden irrigation", "applicability": "flowers", "confidence": 0.9},
    ],
)
async def test_router_excludes_untrusted_or_unrelated_experience(changes):
    repo, record = setup_store()
    record = ExperienceRecord.model_validate({**record.model_dump(), **changes})
    await repo.upsert("experience", str(record.id), record.model_dump(mode="json"))
    bundle = await MemoryExperienceRouter(repo).build_context_bundle(
        "task_execution", "deployment checks"
    )
    assert bundle.experience_context == ()


async def test_router_matches_natural_unsegmented_chinese():
    repo, record = setup_store()
    record = ExperienceRecord.model_validate(
        {
            **record.model_dump(),
            "statement": "部署调试时先检查服务健康状态",
            "applicability": "机器人故障排查",
        }
    )
    await repo.upsert("experience", str(record.id), record.model_dump(mode="json"))
    irrelevant = ExperienceRecord.model_validate(
        {
            **record.model_dump(),
            "id": uuid4(),
            "statement": "园艺经验",
            "applicability": "花草养护",
            "confidence": 0.99,
        }
    )
    await repo.upsert("experience", str(irrelevant.id), irrelevant.model_dump(mode="json"))
    bundle = await MemoryExperienceRouter(repo).build_context_bundle(
        "task_execution", "帮我排查部署失败的原因", limit=1
    )
    assert len(bundle.experience_context) == 1
    assert "部署调试" in bundle.experience_context[0]
    unrelated = await MemoryExperienceRouter(repo).build_context_bundle(
        "task_execution", "今天晚饭吃什么"
    )
    assert unrelated.experience_context == ()


async def test_router_limit_is_monotonic():
    repo, record = setup_store()
    for _ in range(9):
        item = ExperienceRecord.model_validate({**record.model_dump(), "id": uuid4()})
        await repo.upsert("experience", str(item.id), item.model_dump(mode="json"))
    sizes = [
        len(
            (
                await MemoryExperienceRouter(repo).build_context_bundle(
                    "task_execution", "deployment", limit=n
                )
            ).experience_context
        )
        for n in (0, 1, 7, 8, 9)
    ]
    assert sizes == [0, 1, 7, 8, 8]


async def test_router_ignores_shared_function_words_as_relevance():
    repo, record = setup_store()
    record = ExperienceRecord.model_validate({
        **record.model_dump(), "statement": "The user prefers garden irrigation",
        "applicability": "Use this for the flowers", "confidence": 0.9,
    })
    await repo.upsert("experience", str(record.id), record.model_dump(mode="json"))
    bundle = await MemoryExperienceRouter(repo).build_context_bundle(
        "task_execution", "Please help the user with this deployment failure")
    assert bundle.experience_context == ()


@pytest.mark.parametrize("unsafe", [True, False])
async def test_world_state_evidence_merge_is_safe_and_bounded(unsafe):
    repo, record = setup_store()
    service = WorldStateService(repo)
    item = WorldStateItem(
        tenant_id=record.tenant_id,
        user_id=record.user_id,
        entity_type="task",
        name="deployment",
        state="pending",
        evidence_refs=(evidence(),),
    )
    await service.upsert_item(item)
    if unsafe:
        before = await repo.get("world_state", str(item.id))
        with pytest.raises(ValueError, match="unsafe"):
            await service.mark_status(
                item.id,
                "completed",
                EvidenceRef(kind="episode", ref_id="unsafe", summary="password=private"),
            )
        assert await repo.get("world_state", str(item.id)) == before
    else:
        for index in range(1, 22):
            updated = await service.mark_status(item.id, "active", evidence(index))
            assert len(updated.evidence_refs) <= 16


@pytest.mark.parametrize("field", ["kind", "ref_id"])
async def test_unsafe_episode_evidence_identity_is_rejected_before_promotion(field):
    repo, record = setup_store()
    unsafe = EvidenceRef.model_validate({**evidence().model_dump(), field: "password=private"})
    episode = CognitiveEpisode(
        tenant_id=record.tenant_id,
        user_id=record.user_id,
        source="voice",
        started_at=datetime.now(UTC),
        summary="voice correction",
        signals=("user_corrected",),
        evidence_refs=(unsafe,),
    )
    result = await ExperienceStore(repo).record_episode(episode)
    assert result.rejection_reason == "unsafe_content"
    assert await repo.list("experience") == ()
