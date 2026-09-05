"""Robot device API.

Register with the FastAPI app when wiring companion product routes:

    from agent_hub.api.routers import robot
    application.include_router(robot.router)
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field

from agent_hub.companion.proactive import ProactiveEngine
from agent_hub.companion.state import CompanionStateService
from agent_hub.companion.timeline import LifeTimelineService
from agent_hub.companion.types import CompanionState, LifeEvent
from agent_hub.robot.bridge import RobotBridgeHub
from agent_hub.robot.devices import DeviceRegistry
from agent_hub.robot.sessions import RobotSessionStore
from agent_hub.robot.types import BridgeEnvelope

router = APIRouter(prefix="/api/robot/v1", tags=["robot"])

_devices = DeviceRegistry()
_sessions = RobotSessionStore()
_companion_states = CompanionStateService()
_timeline = LifeTimelineService()
_proactive = ProactiveEngine()
_bridge = RobotBridgeHub(_companion_states)
_bootstrap_tenant = UUID("00000000-0000-4000-8000-000000000001")
_bootstrap_user = UUID("00000000-0000-4000-8000-000000000002")


class DeviceRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    device_id: str = Field(min_length=1, max_length=128)


class DeviceRegisterResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    device_id: str
    device_token: str


class CompanionStatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    persona_id: str | None = None
    relationship_level: int | None = Field(default=None, ge=0, le=100)
    mood: str | None = None
    scene: str | None = None
    last_user_topics: list[str] | None = None


class LifeEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    title: str = Field(min_length=1, max_length=256)
    summary: str = Field(min_length=1, max_length=4096)
    occurred_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)


@router.post("/devices/register", response_model=DeviceRegisterResponse)
async def register_device(body: DeviceRegisterRequest) -> DeviceRegisterResponse:
    record = _devices.register(
        device_id=body.device_id,
        tenant_id=_bootstrap_tenant,
        user_id=_bootstrap_user,
    )
    return DeviceRegisterResponse(device_id=record.device_id, device_token=record.device_token)


@router.get("/companion-state", response_model=CompanionState)
async def get_companion_state(device_id: str) -> CompanionState:
    record = _devices.get(device_id)
    if record is None:
        return _companion_states.get(_bootstrap_tenant, _bootstrap_user)
    return _companion_states.get(record.tenant_id, record.user_id)


@router.patch("/companion-state", response_model=CompanionState)
async def patch_companion_state(device_id: str, body: CompanionStatePatch) -> CompanionState:
    record = _devices.get(device_id)
    tenant_id = record.tenant_id if record else _bootstrap_tenant
    user_id = record.user_id if record else _bootstrap_user
    updates = body.model_dump(exclude_none=True)
    return _companion_states.patch(tenant_id, user_id, **updates)


@router.get("/timeline", response_model=list[LifeEvent])
async def list_timeline(device_id: str, limit: int = 50) -> list[LifeEvent]:
    record = _devices.get(device_id)
    user_id = record.user_id if record else _bootstrap_user
    return list(_timeline.list_for_user(user_id, limit=limit))


@router.post("/timeline", response_model=LifeEvent)
async def create_timeline_event(device_id: str, body: LifeEventCreate) -> LifeEvent:
    record = _devices.get(device_id)
    user_id = record.user_id if record else _bootstrap_user
    return _timeline.add(
        user_id=user_id,
        title=body.title,
        summary=body.summary,
        occurred_at=body.occurred_at,
        tags=body.tags,
    )


@router.get("/proactive/suggest")
async def suggest_proactive(device_id: str) -> dict[str, str | None]:
    record = _devices.get(device_id)
    tenant_id = record.tenant_id if record else _bootstrap_tenant
    user_id = record.user_id if record else _bootstrap_user
    state = _companion_states.get(tenant_id, user_id)
    return {"text": _proactive.suggest_next_nudge(state)}


@router.websocket("/ws")
async def robot_ws(
    websocket: WebSocket,
    x_device_token: str | None = Header(default=None, alias="X-Device-Token"),
) -> None:
    await websocket.accept()
    token = x_device_token or websocket.query_params.get("device_token")
    if not token:
        await websocket.close(code=4401)
        return
    device = _devices.authenticate(token)
    if device is None:
        await websocket.close(code=4401)
        return
    session = _sessions.create(
        device_id=device.device_id,
        tenant_id=device.tenant_id,
        user_id=device.user_id,
    )
    try:
        while True:
            data = await websocket.receive_json()
            envelope = BridgeEnvelope.model_validate(data)
            for response in _bridge.handle_device_message(session, envelope):
                await websocket.send_json(response.model_dump(mode="json"))
    except WebSocketDisconnect:
        _sessions.end(session.session_id)
