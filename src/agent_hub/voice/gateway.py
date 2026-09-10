from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agent_hub.robot.protocol import RobotEnvelope
from agent_hub.robot.session import RobotSessionRegistry, RobotStatusSnapshot
from agent_hub.voice.companion import CompanionResponder


def create_robot_voice_router(
    registry: RobotSessionRegistry | None = None,
    responder: CompanionResponder | None = None,
) -> APIRouter:
    active_responder = responder or CompanionResponder()
    active_registry = registry or RobotSessionRegistry(responder=active_responder.respond_text)
    router = APIRouter(prefix="/api/v1/robot", tags=["robot"])

    @router.get("/devices", response_model=RobotStatusSnapshot)
    async def list_devices(device_id: str | None = None) -> RobotStatusSnapshot:
        return active_registry.status(device_id)

    @router.websocket("/ws/{device_id}")
    async def robot_websocket(websocket: WebSocket, device_id: str) -> None:
        await websocket.accept()
        try:
            while True:
                envelope = RobotEnvelope.model_validate_json(await websocket.receive_text())
                if envelope.device_id != device_id:
                    await websocket.close(code=1008)
                    return
                for response in active_registry.record(envelope):
                    await websocket.send_json(response.model_dump(mode="json"))
        except WebSocketDisconnect:
            return

    return router
