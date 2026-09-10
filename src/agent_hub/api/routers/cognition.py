from __future__ import annotations

from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_hub.api.dependencies import require_permission
from agent_hub.api.errors import BASE_ERROR_RESPONSES, PublicAPIError, error_responses
from agent_hub.auth.models import AuthenticatedPrincipal
from agent_hub.cognition.experience_store import EpisodeIngestResult, ExperienceStore
from agent_hub.cognition.repository import (
    AdminResourceCognitionRepository,
    CognitionRepository,
)
from agent_hub.cognition.router import MemoryExperienceRouter
from agent_hub.cognition.types import (
    BeliefRecord,
    CognitiveContextBundle,
    CognitiveEpisode,
    EvidenceRef,
    ExperienceRecord,
    ReflectionRecord,
    RelationshipState,
    WorldStateItem,
)

router = APIRouter(
    prefix="/api/v1/admin/cognition",
    tags=["admin", "cognition"],
    responses={**BASE_ERROR_RESPONSES, **error_responses(401, 403, 422, 503)},
)

class ExperienceOutcomeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    succeeded: bool
    evidence: EvidenceRef


class RouterPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene: str = Field(min_length=1, max_length=128)
    current_request: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=8, ge=1, le=8)


async def cognition_repository(
    request: Request,
    principal: Annotated[
        AuthenticatedPrincipal, Depends(require_permission("cognition:read"))
    ],
) -> CognitionRepository:
    return _repository_for_principal(request, principal)


async def writable_cognition_repository(
    request: Request,
    principal: Annotated[
        AuthenticatedPrincipal, Depends(require_permission("cognition:write"))
    ],
) -> CognitionRepository:
    return _repository_for_principal(request, principal)


@router.get("/episodes", response_model=list[CognitiveEpisode])
async def list_episodes(
    repository: Annotated[CognitionRepository, Depends(cognition_repository)],
) -> list[CognitiveEpisode]:
    return await _list_records(repository, "episode", CognitiveEpisode)


@router.post("/episodes", response_model=EpisodeIngestResult)
async def post_episode(
    body: Annotated[dict[str, Any], Body()],
    repository: Annotated[CognitionRepository, Depends(writable_cognition_repository)],
    principal: Annotated[
        AuthenticatedPrincipal, Depends(require_permission("cognition:write"))
    ],
) -> EpisodeIngestResult:
    values = dict(body)
    values["tenant_id"] = principal.tenant_id
    values["user_id"] = principal.user_id
    try:
        episode = CognitiveEpisode.model_validate(values)
    except ValidationError:
        raise PublicAPIError(422, "request_validation", "request validation failed") from None
    return await ExperienceStore(repository).record_episode(episode)


@router.get("/experiences", response_model=list[ExperienceRecord])
async def list_experiences(
    repository: Annotated[CognitionRepository, Depends(cognition_repository)],
) -> list[ExperienceRecord]:
    return await _list_records(repository, "experience", ExperienceRecord)


@router.post("/experiences/{experience_id}/outcome", response_model=ExperienceRecord)
async def post_experience_outcome(
    experience_id: UUID,
    body: ExperienceOutcomeRequest,
    repository: Annotated[CognitionRepository, Depends(writable_cognition_repository)],
) -> ExperienceRecord:
    try:
        return await ExperienceStore(repository).record_outcome(
            experience_id,
            succeeded=body.succeeded,
            evidence=body.evidence,
        )
    except LookupError:
        raise PublicAPIError(404, "not_found", "not found") from None
    except ValueError:
        raise PublicAPIError(422, "invalid_evidence", "Evidence is unsafe or invalid") from None


@router.get("/reflections", response_model=list[ReflectionRecord])
async def list_reflections(
    repository: Annotated[CognitionRepository, Depends(cognition_repository)],
) -> list[ReflectionRecord]:
    return await _list_records(repository, "reflection", ReflectionRecord)


@router.get("/beliefs", response_model=list[BeliefRecord])
async def list_beliefs(
    repository: Annotated[CognitionRepository, Depends(cognition_repository)],
) -> list[BeliefRecord]:
    return await _list_records(repository, "belief", BeliefRecord)


@router.get("/relationship", response_model=list[RelationshipState])
async def list_relationship(
    repository: Annotated[CognitionRepository, Depends(cognition_repository)],
) -> list[RelationshipState]:
    return await _list_records(
        repository,
        "relationship",
        RelationshipState,
        strip_repository_id=True,
    )


@router.get("/world-state", response_model=list[WorldStateItem])
async def list_world_state(
    repository: Annotated[CognitionRepository, Depends(cognition_repository)],
) -> list[WorldStateItem]:
    return await _list_records(repository, "world_state", WorldStateItem)


@router.post("/router-preview", response_model=CognitiveContextBundle)
async def router_preview(
    body: RouterPreviewRequest,
    repository: Annotated[CognitionRepository, Depends(cognition_repository)],
) -> CognitiveContextBundle:
    return await MemoryExperienceRouter(repository).build_context_bundle(
        scene=body.scene,
        current_request=body.current_request,
        limit=body.limit,
    )


def _repository_for_principal(
    request: Request, principal: AuthenticatedPrincipal
) -> CognitionRepository:
    factory = getattr(request.app.state, "cognition_repository_factory", None)
    if callable(factory):
        return cast(
            CognitionRepository,
            factory(tenant_id=principal.tenant_id, user_id=principal.user_id),
        )

    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise PublicAPIError(503, "service_unavailable", "service unavailable")
    return AdminResourceCognitionRepository(
        session_factory=session_factory,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
    )


async def _list_records(
    repository: CognitionRepository,
    record_type: str,
    model: type[BaseModel],
    *,
    strip_repository_id: bool = False,
) -> list[Any]:
    records: list[Any] = []
    for payload in await repository.list(record_type):
        values = _model_payload(payload, model)
        if strip_repository_id:
            values.pop("id", None)
        try:
            records.append(model.model_validate(values))
        except ValidationError:
            continue
    return records


def _model_payload(payload: dict[str, object], model: type[BaseModel]) -> dict[str, object]:
    values = dict(payload)
    values.pop("record_type", None)
    for scoped_field in ("tenant_id", "user_id"):
        if scoped_field not in model.model_fields:
            values.pop(scoped_field, None)
    return values
