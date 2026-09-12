from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field

from agent_hub.api.dependencies import require_permission
from agent_hub.api.errors import BASE_ERROR_RESPONSES, PublicAPIError, error_responses
from agent_hub.auth.models import AuthenticatedPrincipal
from agent_hub.robot.auth import RobotDeviceTokenStore
from agent_hub.robot.ota import OtaArtifact, OtaDecision, OtaManifest, validate_manifest_for_device
from agent_hub.robot.protocol import RobotEnvelope, RobotMessageType, build_envelope
from agent_hub.robot.session import RobotSessionRegistry, RobotStatusSnapshot
from agent_hub.voice.companion import CompanionResponder
from agent_hub.voice.media import VoiceMediaService


class MockUtteranceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    device_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(default="mock-session", min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=4_000)


class MockUtteranceResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    responses: tuple[RobotEnvelope, ...]


class OtaManifestResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    manifest: OtaManifest
    decision: OtaDecision


def _default_ota_manifest() -> OtaManifest:
    return OtaManifest(
        version="2026.09.10+1",
        channel="stable",
        min_protocol_version="1",
        artifact=OtaArtifact(
            url="https://updates.example.com/cube-robot-runtime-2026.09.10+1.tar.gz",
            sha256="0" * 64,
            size_bytes=1,
        ),
        signature="test-signature",
    )


def create_robot_voice_router(
    registry: RobotSessionRegistry | None = None,
    responder: CompanionResponder | None = None,
    device_tokens: RobotDeviceTokenStore | None = None,
    ota_manifest: OtaManifest | None = None,
    media_service: VoiceMediaService | None = None,
    media_service_provider: Callable[[], VoiceMediaService | None] | None = None,
) -> APIRouter:
    active_responder = responder or CompanionResponder()
    active_registry = registry or RobotSessionRegistry(responder=active_responder.respond_text)
    active_device_tokens = device_tokens or RobotDeviceTokenStore.from_secret(None)
    active_ota_manifest = ota_manifest or _default_ota_manifest()
    active_media_service = media_service
    router = APIRouter(prefix="/api/v1/robot", tags=["robot"], responses=BASE_ERROR_RESPONSES)

    @router.get(
        "/devices",
        response_model=RobotStatusSnapshot,
        responses=error_responses(401, 403, 422),
    )
    async def list_devices(
        _principal: Annotated[
            AuthenticatedPrincipal, Depends(require_permission("robot:read"))
        ],
        device_id: str | None = None,
    ) -> RobotStatusSnapshot:
        return active_registry.status(device_id)

    @router.post(
        "/mock-utterance",
        response_model=MockUtteranceResponse,
        responses=error_responses(401, 403, 422),
    )
    async def mock_utterance(
        request: MockUtteranceRequest,
        _principal: Annotated[
            AuthenticatedPrincipal, Depends(require_permission("robot:use"))
        ],
    ) -> MockUtteranceResponse:
        responses = await active_registry.record_async(
            build_envelope(
                message_type=RobotMessageType.SPEECH_PARTIAL,
                device_id=request.device_id,
                session_id=request.session_id,
                payload={"text": request.text, "is_final": True},
            )
        )
        return MockUtteranceResponse(responses=responses)

    @router.get(
        "/ota/manifest/{device_id}",
        response_model=OtaManifestResponse,
        responses=error_responses(401, 422),
    )
    async def get_ota_manifest(
        device_id: str,
        token_header: Annotated[str | None, Header(alias="X-Robot-Device-Token")] = None,
        token_query: Annotated[str | None, Query(alias="device_token")] = None,
        current_version: str = "2026.09.10+0",
        protocol_version: str = "1",
    ) -> OtaManifestResponse:
        _require_device_token(active_device_tokens, device_id, token_header or token_query)
        try:
            decision = validate_manifest_for_device(
                active_ota_manifest,
                protocol_version=protocol_version,
                current_version=current_version,
            )
        except ValueError as error:
            raise PublicAPIError(
                422,
                "request_validation",
                "request validation failed",
                details={"reason": str(error)},
            ) from error
        return OtaManifestResponse(
            manifest=active_ota_manifest,
            decision=decision,
        )

    @router.websocket("/ws/{device_id}")
    async def robot_websocket(websocket: WebSocket, device_id: str) -> None:
        await websocket.accept()
        if not _websocket_device_token_valid(active_device_tokens, websocket, device_id):
            await websocket.close(code=1008)
            return
        try:
            while True:
                envelope = RobotEnvelope.model_validate_json(await websocket.receive_text())
                if envelope.device_id != device_id:
                    await websocket.close(code=1008)
                    return
                media = (
                    media_service_provider()
                    if media_service_provider is not None
                    else active_media_service
                )
                if media is not None and envelope.type in {
                    RobotMessageType.AUDIO_START,
                    RobotMessageType.AUDIO_CHUNK,
                    RobotMessageType.AUDIO_END,
                }:
                    responses = await media.handle(envelope)
                else:
                    responses = await active_registry.record_async(envelope)
                for response in responses:
                    await websocket.send_json(response.model_dump(mode="json"))
        except WebSocketDisconnect:
            return

    return router


def _require_device_token(
    tokens: RobotDeviceTokenStore,
    device_id: str,
    provided_token: str | None,
) -> None:
    if not tokens.authenticate(device_id, provided_token):
        raise PublicAPIError(401, "invalid_robot_device_token", "invalid robot device token")


def _websocket_device_token_valid(
    tokens: RobotDeviceTokenStore,
    websocket: WebSocket,
    device_id: str,
) -> bool:
    header_token = websocket.headers.get("x-robot-device-token")
    query_token = websocket.query_params.get("device_token")
    return tokens.authenticate(device_id, header_token or query_token)
