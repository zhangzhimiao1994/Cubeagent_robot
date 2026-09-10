from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.websockets import WebSocketDisconnect

from agent_hub.app import create_app
from agent_hub.auth.models import AuthenticatedPrincipal, InvalidCredentials, Role
from agent_hub.robot.protocol import RobotMessageType, build_envelope
from agent_hub.settings import Settings


class StubAuthService:
    def authenticate_token(self, token: str) -> AuthenticatedPrincipal:
        if token != "valid-token":
            raise InvalidCredentials("bad token")
        return AuthenticatedPrincipal(
            user_id=UUID("00000000-0000-4000-8000-000000000101"),
            tenant_id=UUID("00000000-0000-4000-8000-000000000201"),
            role=Role.ADMIN,
        )


def _client() -> TestClient:
    return TestClient(
        create_app(
            auth_service=StubAuthService(),
            settings=Settings(robot_device_tokens=SecretStr("pi-lab-01:robot-token")),
        )
    )


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer valid-token"}


def _device_headers() -> dict[str, str]:
    return {"x-robot-device-token": "robot-token"}


def test_robot_status_endpoint_requires_management_auth() -> None:
    client = _client()

    response = client.get("/api/v1/robot/devices")

    assert response.status_code == 401


def test_robot_status_endpoint_uses_runtime_registry() -> None:
    client = _client()

    response = client.get("/api/v1/robot/devices", headers=_headers())

    assert response.status_code == 200
    assert response.json()["devices"] == []


def test_robot_websocket_rejects_missing_device_token() -> None:
    client = _client()

    with (
        pytest.raises(WebSocketDisconnect) as caught,
        client.websocket_connect("/api/v1/robot/ws/pi-lab-01") as ws,
    ):
        ws.receive_json()

    assert caught.value.code == 1008


def test_robot_websocket_accepts_heartbeat_and_final_utterance() -> None:
    client = _client()

    with client.websocket_connect("/api/v1/robot/ws/pi-lab-01", headers=_device_headers()) as ws:
        ws.send_json(
            build_envelope(
                message_type=RobotMessageType.DEVICE_HEARTBEAT,
                device_id="pi-lab-01",
                session_id="voice-session-1",
                payload={"runtime_version": "0.1.0"},
            ).model_dump(mode="json")
        )
        ws.send_json(
            build_envelope(
                message_type=RobotMessageType.SPEECH_PARTIAL,
                device_id="pi-lab-01",
                session_id="voice-session-1",
                payload={"text": "测试语音", "is_final": True},
            ).model_dump(mode="json")
        )

        message = ws.receive_json()

    assert message["type"] == "assistant.text.done"
    assert "测试语音" in message["payload"]["text"]


def test_robot_mock_utterance_endpoint_requires_management_auth_and_returns_response() -> None:
    client = _client()

    denied = client.post(
        "/api/v1/robot/mock-utterance",
        json={"device_id": "pi-lab-01", "text": "你好"},
    )
    accepted = client.post(
        "/api/v1/robot/mock-utterance",
        headers=_headers(),
        json={"device_id": "pi-lab-01", "text": "你好"},
    )

    assert denied.status_code == 401
    assert accepted.status_code == 200
    body = accepted.json()
    assert body["responses"][0]["type"] == "assistant.text.done"
    assert "你好" in body["responses"][0]["payload"]["text"]


def test_robot_ota_manifest_requires_bound_device_token() -> None:
    client = _client()

    denied = client.get(
        "/api/v1/robot/ota/manifest/pi-lab-01",
        headers={"x-robot-device-token": "wrong"},
    )
    accepted = client.get(
        "/api/v1/robot/ota/manifest/pi-lab-01",
        headers=_device_headers(),
        params={"current_version": "2026.09.10+0", "protocol_version": "1"},
    )

    assert denied.status_code == 401
    assert accepted.status_code == 200
    body = accepted.json()
    assert body["manifest"]["min_protocol_version"] == "1"
    assert body["decision"]["status"] in {"update_available", "up_to_date", "downgrade_blocked"}


def test_robot_device_tokens_are_loaded_from_environment_when_settings_are_not_injected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_HUB_ROBOT_DEVICE_TOKENS", "pi-lab-01:robot-token")
    client = TestClient(create_app())

    response = client.get(
        "/api/v1/robot/ota/manifest/pi-lab-01",
        headers=_device_headers(),
        params={"current_version": "2026.09.10+0", "protocol_version": "1"},
    )

    assert response.status_code == 200
