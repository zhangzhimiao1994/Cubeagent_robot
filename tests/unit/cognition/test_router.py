from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from agent_hub.cognition.repository import InMemoryCognitionRepository
from agent_hub.cognition.router import MemoryExperienceRouter, render_cognitive_context
from agent_hub.cognition.types import (
    BeliefRecord,
    BeliefStatus,
    CognitiveContextBundle,
    CognitiveRecordStatus,
    EvidenceRef,
    ExperienceKind,
    ExperienceRecord,
    RelationshipState,
    SelfModelRecord,
    WorldEntityType,
    WorldStateItem,
)


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


@pytest.mark.asyncio
async def test_router_scores_filters_and_renders_experience_context() -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    repo = InMemoryCognitionRepository(tenant_id=tenant_id, user_id=user_id)
    evidence = EvidenceRef(kind="episode", ref_id="ep-score", summary="scoring")
    contradiction = EvidenceRef(kind="episode", ref_id="ep-wrong", summary="wrong")
    now = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)
    older = now - timedelta(minutes=5)
    stale = ExperienceRecord(
        tenant_id=tenant_id,
        user_id=user_id,
        kind=ExperienceKind.VOICE_INTERACTION,
        statement="Stale deployment debugging advice",
        applicability="deployment debugging",
        confidence=1.0,
        evidence_refs=(evidence,),
        status=CognitiveRecordStatus.STALE,
        updated_at=now + timedelta(minutes=1),
    )
    low_conflict = ExperienceRecord(
        tenant_id=tenant_id,
        user_id=user_id,
        kind=ExperienceKind.STRATEGY,
        statement="Deployment debugging with contradicted low confidence",
        applicability="deployment debugging",
        confidence=0.5,
        evidence_refs=(evidence,),
        contradictions=(contradiction,),
        status=CognitiveRecordStatus.ACTIVE,
        updated_at=now,
    )
    voice = ExperienceRecord(
        tenant_id=tenant_id,
        user_id=user_id,
        kind=ExperienceKind.VOICE_INTERACTION,
        statement="Voice deployment debugging should start with the next command",
        applicability="deployment debugging",
        recommended_action="Keep spoken answers short.",
        confidence=0.7,
        evidence_refs=(evidence,),
        status=CognitiveRecordStatus.CANDIDATE,
        updated_at=older,
    )
    await repo.upsert("experience", str(stale.id), stale.model_dump(mode="json"))
    await repo.upsert("experience", str(low_conflict.id), low_conflict.model_dump(mode="json"))
    await repo.upsert("experience", str(voice.id), voice.model_dump(mode="json"))

    bundle = await MemoryExperienceRouter(repo).build_context_bundle(
        scene="voice_chat",
        current_request="deployment debugging",
        limit=2,
    )
    rendered = render_cognitive_context(bundle)

    assert "Voice deployment debugging should start" in bundle.experience_context[0]
    assert "Stale deployment debugging advice" not in rendered
    assert "contradicted low confidence" in rendered
    assert rendered.startswith("<COGNITIVE_CONTEXT>")
    assert rendered.endswith("</COGNITIVE_CONTEXT>")


@pytest.mark.asyncio
async def test_router_builds_bounded_bundle_from_cognitive_records() -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    repo = InMemoryCognitionRepository(tenant_id=tenant_id, user_id=user_id)
    evidence = EvidenceRef(kind="conversation", ref_id="conv-1", summary="context")
    self_model = SelfModelRecord(
        tenant_id=tenant_id,
        user_id=user_id,
        identity="Embodied voice companion for local robot work.",
        personality="Direct and practical.",
        capability_boundaries=("Never claim deployment success before checking health.",),
        evidence_refs=(evidence,),
        status=CognitiveRecordStatus.ACTIVE,
    )
    relationship = RelationshipState(
        tenant_id=tenant_id,
        user_id=user_id,
        preferred_tone="direct",
        preferred_depth="concise",
        stable_preferences=("Use concise spoken debugging steps.",),
        boundaries=("Ask before making provider-quota changes.",),
        evidence_refs=(evidence,),
        status=CognitiveRecordStatus.ACTIVE,
    )
    preference = ExperienceRecord(
        tenant_id=tenant_id,
        user_id=user_id,
        kind=ExperienceKind.PREFERENCE,
        statement="User prefers direct deployment answers.",
        applicability="deployment debugging",
        recommended_action="Start with the concrete next action.",
        confidence=0.8,
        evidence_refs=(evidence,),
        status=CognitiveRecordStatus.ACTIVE,
    )
    belief = BeliefRecord(
        tenant_id=tenant_id,
        user_id=user_id,
        subject="user",
        predicate="prefers",
        object="short voice replies",
        evidence_refs=(evidence,),
        confidence=0.8,
        status=BeliefStatus.ACTIVE,
    )
    world_items = [
        WorldStateItem(
            tenant_id=tenant_id,
            user_id=user_id,
            entity_type=WorldEntityType.TASK,
            name=f"deploy target {index}",
            state="needs health check",
            status="active",
            evidence_refs=(evidence,),
        )
        for index in range(3)
    ]
    await repo.upsert("self_model", "self", self_model.model_dump(mode="json"))
    await repo.upsert("relationship", f"{tenant_id}:{user_id}", relationship.model_dump(mode="json"))
    await repo.upsert("experience", str(preference.id), preference.model_dump(mode="json"))
    await repo.upsert("belief", str(belief.id), belief.model_dump(mode="json"))
    for item in world_items:
        await repo.upsert("world_state", str(item.id), item.model_dump(mode="json"))
    await repo.upsert(
        "skill",
        "skill-1",
        {
            "name": "deployment_probe",
            "recommendation": "Run a health probe before reporting deployment status.",
            "status": CognitiveRecordStatus.ACTIVE.value,
            "confidence": 0.7,
        },
    )
    await repo.upsert(
        "protected_change_proposal",
        "proposal-1",
        {
            "target": "self_model",
            "proposed_change": "Rewrite core identity without approval.",
            "status": CognitiveRecordStatus.CANDIDATE.value,
        },
    )

    bundle = await MemoryExperienceRouter(repo).build_context_bundle(
        scene="voice_chat",
        current_request="deployment debugging",
    )
    rendered = render_cognitive_context(bundle)

    assert len(bundle.core_constraints) == 1
    assert len(bundle.relationship_context) == 3
    assert len(bundle.world_context) == 2
    assert len(bundle.skill_context) == 1
    assert "unconfirmed" not in rendered.casefold()
    assert "Rewrite core identity" not in rendered
    assert "Run a health probe" in rendered


def test_render_cognitive_context_returns_empty_string_for_empty_bundle() -> None:
    assert render_cognitive_context(CognitiveContextBundle()) == ""
