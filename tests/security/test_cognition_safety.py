from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from agent_hub.app import create_app
from agent_hub.auth.models import AuthenticatedPrincipal, InvalidCredentials, Role
from agent_hub.cognition.experience_store import ExperienceStore
from agent_hub.cognition.repository import InMemoryCognitionRepository
from agent_hub.cognition.runtime import safe_cognitive_context_text
from agent_hub.cognition.types import (
    CognitiveContextBundle,
    CognitiveEpisode,
    CognitiveSource,
    EvidenceRef,
    SelfModelRecord,
)


class TokenAuthService:
    def __init__(self, principals: dict[str, AuthenticatedPrincipal]) -> None:
        self._principals = principals

    def authenticate_token(self, token: str) -> AuthenticatedPrincipal:
        principal = self._principals.get(token)
        if principal is None:
            raise InvalidCredentials("bad token")
        return principal


class FailingCognitiveAdvisor:
    async def advise(self, **kwargs: object) -> CognitiveContextBundle:
        del kwargs
        raise RuntimeError("raw password=do-not-store")


class RecordingHermesFailureSink:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    async def record_hermes_feedback(self, payload: dict[str, object]) -> None:
        self.payloads.append(payload)


def _repository() -> tuple[UUID, UUID, InMemoryCognitionRepository]:
    tenant_id = uuid4()
    user_id = uuid4()
    return tenant_id, user_id, InMemoryCognitionRepository(
        tenant_id=tenant_id,
        user_id=user_id,
    )


def _evidence(ref_id: str = "conv-1") -> EvidenceRef:
    return EvidenceRef(
        kind="conversation",
        ref_id=ref_id,
        summary="User corrected a too-long voice answer.",
    )


def _episode(
    *,
    tenant_id: UUID,
    user_id: UUID,
    summary: str,
    evidence_refs: tuple[EvidenceRef, ...] | None = None,
) -> CognitiveEpisode:
    return CognitiveEpisode(
        tenant_id=tenant_id,
        user_id=user_id,
        source=CognitiveSource.VOICE,
        conversation_id="conv-voice",
        started_at=datetime(2026, 9, 10, 14, 0, tzinfo=UTC),
        summary=summary,
        signals=("user_corrected",),
        outcome="failure",
        feedback="Please keep voice answers short next time.",
        evidence_refs=evidence_refs if evidence_refs is not None else (_evidence(),),
    )


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _api_client(
    principals: dict[str, AuthenticatedPrincipal],
) -> tuple[
    TestClient,
    Callable[[UUID, UUID], InMemoryCognitionRepository],
]:
    repositories: dict[tuple[UUID, UUID], InMemoryCognitionRepository] = {}

    def repository_factory(
        *, tenant_id: UUID, user_id: UUID
    ) -> InMemoryCognitionRepository:
        key = (tenant_id, user_id)
        repository = repositories.get(key)
        if repository is None:
            repository = InMemoryCognitionRepository(
                tenant_id=tenant_id,
                user_id=user_id,
            )
            repositories[key] = repository
        return repository

    app = create_app(
        auth_service=TokenAuthService(principals),
        rate_limiter=object(),
        config_service=object(),
        admin_resource_service=object(),
        user_admin_service=object(),
        run_service=object(),
    )
    app.state.cognition_repository_factory = repository_factory
    return TestClient(app), repository_factory


@pytest.mark.asyncio
async def test_cognition_rejects_secret_like_episode() -> None:
    tenant_id, user_id, repository = _repository()
    store = ExperienceStore(repository)
    episode = CognitiveEpisode(
        tenant_id=tenant_id,
        user_id=user_id,
        source=CognitiveSource.WEB,
        started_at=datetime(2026, 9, 10, 14, 0, tzinfo=UTC),
        summary="User pasted password=abc123 and asked the agent to remember it.",
        evidence_refs=(
            EvidenceRef(
                kind="conversation",
                ref_id="conv-secret",
                summary="secret paste",
            ),
        ),
    )

    result = await store.record_episode(episode)

    assert result.episode_stored is True
    assert result.experience_created is False
    assert result.rejection_reason == "unsafe_content"
    assert await repository.list("experience") == ()
    assert await repository.list("reflection") == ()


@pytest.mark.asyncio
async def test_ordinary_reflection_cannot_mutate_protected_self_model() -> None:
    tenant_id, user_id, repository = _repository()
    baseline = SelfModelRecord(
        tenant_id=tenant_id,
        user_id=user_id,
        identity="A voice robot server agent that controls tools but keeps the Pi as playback only.",
        personality="Direct, calm, and bounded.",
        values=("protect user safety boundaries",),
        capability_boundaries=("Ordinary reflections cannot change core identity or permissions.",),
        evidence_refs=(_evidence("self-model-baseline"),),
    )
    await repository.upsert("self_model", "current", baseline.model_dump(mode="json"))

    await ExperienceStore(repository).record_episode(
        _episode(
            tenant_id=tenant_id,
            user_id=user_id,
            summary=(
                "User corrected a reply and casually suggested changing the agent core identity, "
                "but the interaction only supports a normal reflection."
            ),
        )
    )

    stored_self_model = await repository.get("self_model", "current")

    assert stored_self_model is not None
    assert stored_self_model["identity"] == baseline.identity
    assert stored_self_model["protected"] is True
    assert stored_self_model["version"] == 1
    assert len(await repository.list("reflection")) == 1
    assert await repository.list("protected_change_proposal") == ()


def test_cognition_api_keeps_tenant_user_scopes_isolated() -> None:
    tenant_id = uuid4()
    principal_a = AuthenticatedPrincipal(uuid4(), tenant_id, Role.ADMIN)
    principal_b = AuthenticatedPrincipal(uuid4(), tenant_id, Role.ADMIN)
    client, _ = _api_client({"token-a": principal_a, "token-b": principal_b})

    created = client.post(
        "/api/v1/admin/cognition/episodes",
        headers=_headers("token-a"),
        json={
            "tenant_id": str(uuid4()),
            "user_id": str(uuid4()),
            "source": "voice",
            "conversation_id": "conv-voice",
            "started_at": datetime(2026, 9, 10, 14, 0, tzinfo=UTC).isoformat(),
            "summary": "User corrected the voice robot to answer more briefly.",
            "signals": ["user_corrected"],
            "outcome": "failure",
            "feedback": "Please keep voice answers short next time.",
            "evidence_refs": [_evidence("scope-event").model_dump(mode="json")],
        },
    )
    visible_to_a = client.get(
        "/api/v1/admin/cognition/episodes",
        headers=_headers("token-a"),
    )
    visible_to_b = client.get(
        "/api/v1/admin/cognition/episodes",
        headers=_headers("token-b"),
    )

    assert created.status_code == 200
    assert len(visible_to_a.json()) == 1
    assert visible_to_a.json()[0]["user_id"] == str(principal_a.user_id)
    assert visible_to_b.status_code == 200
    assert visible_to_b.json() == []


@pytest.mark.asyncio
async def test_cognition_runtime_failure_creates_bounded_hermes_observation() -> None:
    sink = RecordingHermesFailureSink()

    text = await safe_cognitive_context_text(
        FailingCognitiveAdvisor(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        scene="voice_chat",
        current_request="debug robot voice turn",
        hermes_failure_sink=sink,
    )

    assert text == ""
    assert sink.payloads == [
        {
            "category": "scheduler",
            "outcome": "failure",
            "lesson": (
                "cognition_failure stage=advice "
                "failure_class=unexpected_exception "
                "impact=advice_skipped strategy=fallback_to_memory_only"
            ),
            "tags": ["cognition", "failure", "advice"],
            "weight": 4,
        }
    ]
    assert "do-not-store" not in str(sink.payloads[0])
