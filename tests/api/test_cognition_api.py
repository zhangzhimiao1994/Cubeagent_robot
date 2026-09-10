from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from agent_hub.app import create_app
from agent_hub.auth.models import AuthenticatedPrincipal, InvalidCredentials, Role
from agent_hub.cognition.experience_store import ExperienceStore
from agent_hub.cognition.repository import InMemoryCognitionRepository
from agent_hub.cognition.types import (
    BeliefRecord,
    CognitiveEpisode,
    EvidenceRef,
    ReflectionRecord,
    RelationshipState,
    WorldStateItem,
)


class StubAuthService:
    def __init__(self, principal: AuthenticatedPrincipal) -> None:
        self.principal = principal

    def authenticate_token(self, token: str) -> AuthenticatedPrincipal:
        if token != "valid-token":
            raise InvalidCredentials("bad token")
        return self.principal


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer valid-token"}


def _client(
    role: Role,
) -> tuple[TestClient, AuthenticatedPrincipal, Callable[[UUID, UUID], InMemoryCognitionRepository]]:
    principal = AuthenticatedPrincipal(user_id=uuid4(), tenant_id=uuid4(), role=role)
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
        auth_service=StubAuthService(principal),
        rate_limiter=object(),
        config_service=object(),
        admin_resource_service=object(),
        user_admin_service=object(),
        run_service=object(),
    )
    app.state.cognition_repository_factory = repository_factory
    return TestClient(app), principal, repository_factory


def _episode_payload(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "id": str(uuid4()),
        "tenant_id": str(uuid4()),
        "user_id": str(uuid4()),
        "source": "voice",
        "conversation_id": "conv-voice",
        "started_at": datetime(2026, 9, 10, 8, 0, tzinfo=UTC).isoformat(),
        "ended_at": datetime(2026, 9, 10, 8, 1, tzinfo=UTC).isoformat(),
        "summary": "User corrected the voice robot to answer more briefly during wake word chat.",
        "signals": ["user_corrected"],
        "outcome": "failure",
        "feedback": "Please keep voice answers short next time.",
        "evidence_refs": [
            {
                "kind": "run_event",
                "ref_id": "event-1",
                "summary": "User corrected overly long voice response.",
            }
        ],
        "privacy_level": "normal",
    }
    values.update(overrides)
    return values


def _evidence(ref_id: str = "event-1") -> EvidenceRef:
    return EvidenceRef(
        kind="run_event",
        ref_id=ref_id,
        summary="User corrected overly long voice response.",
    )


def test_admin_can_post_episode_and_create_experience() -> None:
    client, _, _ = _client(Role.ADMIN)

    response = client.post(
        "/api/v1/admin/cognition/episodes",
        headers=_headers(),
        json=_episode_payload(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["episode_stored"] is True
    assert body["experience_created"] is True
    assert body["experience"]["kind"] == "failure_pattern"


def test_operator_cannot_write_but_can_read_and_preview() -> None:
    client, principal, repository_factory = _client(Role.OPERATOR)
    repository = repository_factory(tenant_id=principal.tenant_id, user_id=principal.user_id)
    episode = CognitiveEpisode.model_validate(
        {
            **_episode_payload(),
            "tenant_id": principal.tenant_id,
            "user_id": principal.user_id,
        }
    )
    created = asyncio.run(ExperienceStore(repository).record_episode(episode))
    assert created.episode_stored is True

    denied = client.post(
        "/api/v1/admin/cognition/episodes",
        headers=_headers(),
        json=_episode_payload(),
    )
    episodes = client.get("/api/v1/admin/cognition/episodes", headers=_headers())
    preview = client.post(
        "/api/v1/admin/cognition/router-preview",
        headers=_headers(),
        json={
            "scene": "voice_chat",
            "current_request": "voice robot should be brief",
            "limit": 1,
        },
    )

    assert denied.status_code == 403
    assert episodes.status_code == 200
    assert len(episodes.json()) == 1
    assert preview.status_code == 200
    assert len(preview.json()["experience_context"]) <= 1


def test_viewer_cannot_access_cognition_routes() -> None:
    client, _, _ = _client(Role.VIEWER)

    listed = client.get("/api/v1/admin/cognition/episodes", headers=_headers())
    preview = client.post(
        "/api/v1/admin/cognition/router-preview",
        headers=_headers(),
        json={"scene": "voice_chat", "current_request": "hello"},
    )

    assert listed.status_code == 403
    assert preview.status_code == 403


def test_router_preview_returns_bounded_context_after_accepted_episode() -> None:
    client, _, _ = _client(Role.ADMIN)
    created = client.post(
        "/api/v1/admin/cognition/episodes",
        headers=_headers(),
        json=_episode_payload(),
    )
    assert created.status_code == 200

    preview = client.post(
        "/api/v1/admin/cognition/router-preview",
        headers=_headers(),
        json={
            "scene": "voice_chat",
            "current_request": "voice robot wake word chat should be brief",
            "limit": 1,
        },
    )

    assert preview.status_code == 200
    body = preview.json()
    assert len(body["experience_context"]) == 1
    assert "voice robot" in body["experience_context"][0]


def test_episode_body_cannot_override_principal_scope() -> None:
    client, principal, _ = _client(Role.ADMIN)
    spoofed_tenant = uuid4()
    spoofed_user = uuid4()

    response = client.post(
        "/api/v1/admin/cognition/episodes",
        headers=_headers(),
        json=_episode_payload(
            tenant_id=str(spoofed_tenant),
            user_id=str(spoofed_user),
        ),
    )

    assert response.status_code == 200
    episodes = client.get("/api/v1/admin/cognition/episodes", headers=_headers())
    assert episodes.status_code == 200
    stored = episodes.json()[0]
    assert stored["tenant_id"] == str(principal.tenant_id)
    assert stored["user_id"] == str(principal.user_id)


def test_experience_outcome_updates_counts_and_missing_experience_returns_404() -> None:
    client, _, _ = _client(Role.ADMIN)
    created = client.post(
        "/api/v1/admin/cognition/episodes",
        headers=_headers(),
        json=_episode_payload(),
    )
    assert created.status_code == 200
    experience = created.json()["experience"]

    updated = client.post(
        f"/api/v1/admin/cognition/experiences/{experience['id']}/outcome",
        headers=_headers(),
        json={"succeeded": True, "evidence": _evidence("outcome-1").model_dump(mode="json")},
    )
    missing = client.post(
        f"/api/v1/admin/cognition/experiences/{uuid4()}/outcome",
        headers=_headers(),
        json={"succeeded": False, "evidence": _evidence("missing-1").model_dump(mode="json")},
    )

    assert updated.status_code == 200
    body = updated.json()
    assert body["usage_count"] == 1
    assert body["success_count"] == 1
    assert body["failure_count"] == 0
    assert body["confidence"] > experience["confidence"]
    assert missing.status_code == 404


def test_unsafe_outcome_returns_bounded_422_without_changing_experience() -> None:
    client, _, _ = _client(Role.ADMIN)
    with client:
        created = client.post("/api/v1/admin/cognition/episodes", headers=_headers(), json=_episode_payload())
        experience = created.json()["experience"]
        response = client.post(
            f"/api/v1/admin/cognition/experiences/{experience['id']}/outcome",
            headers=_headers(), json={"succeeded": True, "evidence": {
                "kind": "run", "ref_id": "outcome", "summary": "password=private",
            }},
        )
        assert response.status_code == 422
        assert "password=" not in response.text
        stored = client.get("/api/v1/admin/cognition/experiences", headers=_headers()).json()
        assert stored == [experience]


def test_list_reflections_accepts_production_scoped_payload() -> None:
    client, principal, repository_factory = _client(Role.ADMIN)
    repository = repository_factory(tenant_id=principal.tenant_id, user_id=principal.user_id)
    reflection = ReflectionRecord(
        episode_id=uuid4(),
        reflection_type="negative",
        trigger="user_corrected",
        what_happened="The voice robot gave a long answer during a wake word interaction.",
        why_it_happened="The agent selected a detailed strategy for a realtime voice turn.",
        better_next_time="Use a short spoken answer first and ask before expanding.",
        evidence_refs=(_evidence(),),
    )
    payload = {
        **reflection.model_dump(mode="json"),
        "tenant_id": str(principal.tenant_id),
        "user_id": str(principal.user_id),
    }
    asyncio.run(repository.upsert("reflection", str(reflection.id), payload))

    response = client.get("/api/v1/admin/cognition/reflections", headers=_headers())

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(reflection.id)
    assert body[0]["what_happened"] == reflection.what_happened
    assert "tenant_id" not in body[0]
    assert "user_id" not in body[0]


def test_list_state_endpoints_return_valid_records_and_skip_bad_payloads() -> None:
    client, principal, repository_factory = _client(Role.ADMIN)
    repository = repository_factory(tenant_id=principal.tenant_id, user_id=principal.user_id)
    evidence = _evidence()
    belief = BeliefRecord(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        subject="user",
        predicate="prefers",
        object="short spoken answers",
        evidence_refs=(evidence,),
    )
    relationship = RelationshipState(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        shared_history=("User corrected a too-long voice response.",),
        evidence_refs=(evidence,),
    )
    world_item = WorldStateItem(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        entity_type="device",
        name="raspberry pi speaker",
        state="acts as playback endpoint, not the brain",
        evidence_refs=(evidence,),
    )
    asyncio.run(repository.upsert("belief", str(belief.id), belief.model_dump(mode="json")))
    asyncio.run(
        repository.upsert(
            "relationship",
            f"{principal.tenant_id}:{principal.user_id}",
            relationship.model_dump(mode="json"),
        )
    )
    asyncio.run(repository.upsert("world_state", str(world_item.id), world_item.model_dump(mode="json")))
    asyncio.run(repository.upsert("belief", "bad-belief", {"subject": ""}))

    beliefs = client.get("/api/v1/admin/cognition/beliefs", headers=_headers())
    relationship_response = client.get("/api/v1/admin/cognition/relationship", headers=_headers())
    world_state = client.get("/api/v1/admin/cognition/world-state", headers=_headers())

    assert beliefs.status_code == 200
    assert [item["id"] for item in beliefs.json()] == [str(belief.id)]
    assert relationship_response.status_code == 200
    assert len(relationship_response.json()) == 1
    assert relationship_response.json()[0]["preferred_depth"] == "balanced"
    assert world_state.status_code == 200
    assert world_state.json()[0]["id"] == str(world_item.id)
