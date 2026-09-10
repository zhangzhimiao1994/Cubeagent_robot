from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.websockets import WebSocketDisconnect

from agent_hub.app import create_app
from agent_hub.auth.models import AuthenticatedPrincipal, InvalidCredentials, Role
from agent_hub.domain.runs import RunStatus, TaskMode
from agent_hub.robot.protocol import RobotMessageType, build_envelope
from agent_hub.runs.service import SubmittedRun
from agent_hub.settings import Settings
from agent_hub.voice.companion import RobotRunBridge

ROBOT_RUN_ID = UUID("00000000-0000-4000-8000-000000000301")
ROBOT_TENANT_ID = UUID("00000000-0000-4000-8000-000000000201")


class StubAuthService:
    def authenticate_token(self, token: str) -> AuthenticatedPrincipal:
        if token != "valid-token":
            raise InvalidCredentials("bad token")
        return AuthenticatedPrincipal(
            user_id=UUID("00000000-0000-4000-8000-000000000101"),
            tenant_id=ROBOT_TENANT_ID,
            role=Role.ADMIN,
        )


def _client(
    *,
    run_service: object | None = None,
    run_repository: object | None = None,
) -> TestClient:
    app_kwargs: dict[str, object] = {
        "auth_service": StubAuthService(),
        "settings": Settings(robot_device_tokens=SecretStr("pi-lab-01:robot-token")),
    }
    if run_service is not None:
        app_kwargs["run_service"] = run_service
    if run_repository is not None:
        app_kwargs["run_repository"] = run_repository
    return TestClient(
        create_app(**app_kwargs)
    )


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer valid-token"}


def _device_headers() -> dict[str, str]:
    return {"x-robot-device-token": "robot-token"}


class FakeRobotRunService:
    def __init__(self, *, status: RunStatus = RunStatus.QUEUED) -> None:
        self.status = status
        self.submitted: dict[str, object] = {}
        self.submissions: list[dict[str, object]] = []
        self.executed_run_id: UUID | None = None

    async def submit(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        message: str,
        mode: TaskMode,
        conversation_id: str | None = None,
        channel_context: dict[str, str] | None = None,
        idempotency_key: str | None = None,
        **_: object,
    ) -> SubmittedRun:
        self.submitted = {
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "message": message,
            "mode": mode,
            "conversation_id": conversation_id,
            "channel_context": channel_context,
            "idempotency_key": idempotency_key,
        }
        self.submissions.append(self.submitted)
        return SubmittedRun(
            id=ROBOT_RUN_ID,
            tenant_id=tenant_id,
            status=self.status,
            mode=mode,
            decision_token="robot-choice-token" if self.status is RunStatus.WAITING_USER_MODE else None,
            version=1,
            conversation_id=conversation_id,
        )

    async def execute(self, run_id: UUID) -> SubmittedRun:
        self.executed_run_id = run_id
        return SubmittedRun(
            id=run_id,
            tenant_id=UUID("00000000-0000-4000-8000-000000000201"),
            status=RunStatus.COMPLETED,
            mode=TaskMode.AUTO,
            decision_token=None,
            version=2,
            conversation_id="robot-pi-lab-01-voice-session-1",
        )


class WaitingRobotRunService:
    def __init__(self) -> None:
        self.submitted: dict[str, object] = {}

    async def submit(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        message: str,
        mode: TaskMode,
        conversation_id: str | None = None,
        channel_context: dict[str, str] | None = None,
        idempotency_key: str | None = None,
        **_: object,
    ) -> SubmittedRun:
        del actor_id, message, channel_context, idempotency_key
        self.submitted = {"mode": mode, "conversation_id": conversation_id}
        return SubmittedRun(
            id=ROBOT_RUN_ID,
            tenant_id=tenant_id,
            status=RunStatus.WAITING_USER_MODE,
            mode=mode,
            decision_token="robot-choice-token",
            version=1,
            conversation_id=conversation_id,
        )


class FailingRobotRunService:
    async def submit(self, **_: object) -> SubmittedRun:
        raise RuntimeError("run service unavailable")


class FakeRobotRunRepository:
    def __init__(self, artifacts: tuple[dict[str, object], ...]) -> None:
        self._artifacts = artifacts
        self.artifact_calls: list[tuple[UUID, UUID]] = []

    async def artifacts(self, tenant_id: UUID, run_id: UUID) -> tuple[dict[str, object], ...]:
        self.artifact_calls.append((tenant_id, run_id))
        return self._artifacts


def _final_speech_response(
    client: TestClient,
    *,
    text: str = "测试语音",
    message_id: str | None = None,
) -> dict[str, object]:
    with client.websocket_connect("/api/v1/robot/ws/pi-lab-01", headers=_device_headers()) as ws:
        envelope = build_envelope(
            message_type=RobotMessageType.SPEECH_PARTIAL,
            device_id="pi-lab-01",
            session_id="voice-session-1",
            payload={"text": text, "is_final": True},
        )
        if message_id is not None:
            envelope = envelope.model_copy(update={"message_id": message_id})
        ws.send_json(
            envelope.model_dump(mode="json")
        )
        return ws.receive_json()


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


def test_robot_websocket_bridges_final_speech_to_agent_run_artifact() -> None:
    run_service = FakeRobotRunService()
    run_repository = FakeRobotRunRepository(
        (
            {
                "id": str(UUID("00000000-0000-4000-8000-000000000401")),
                "producer": "main_agent",
                "content": {"text": "服务端 Agent 回复"},
            },
        )
    )
    client = _client(run_service=run_service, run_repository=run_repository)

    response = _final_speech_response(client)

    submitted = run_service.submitted
    assert submitted["mode"].value == "auto"
    assert submitted["conversation_id"] == "robot-pi-lab-01-voice-session-1"
    assert submitted["channel_context"]["source_channel"] == "robot_voice"
    assert submitted["channel_context"]["requested_channel_features"] == "voice,audio,robot"
    assert run_service.executed_run_id == ROBOT_RUN_ID
    assert response["type"] == "assistant.text.done"
    assert response["payload"]["text"] == "服务端 Agent 回复"


def test_robot_websocket_uses_final_envelope_message_id_for_run_idempotency() -> None:
    run_service = FakeRobotRunService()
    run_repository = FakeRobotRunRepository(
        (
            {
                "id": str(UUID("00000000-0000-4000-8000-000000000401")),
                "producer": "main_agent",
                "content": {"text": "服务端 Agent 回复"},
            },
        )
    )
    client = _client(run_service=run_service, run_repository=run_repository)

    _final_speech_response(client, text="同一句话", message_id="robot-msg-1")
    _final_speech_response(client, text="同一句话", message_id="robot-msg-1")
    _final_speech_response(client, text="同一句话", message_id="robot-msg-2")

    idempotency_keys = [
        str(submission["idempotency_key"]) for submission in run_service.submissions
    ]
    assert idempotency_keys[0] == idempotency_keys[1]
    assert idempotency_keys[2] != idempotency_keys[0]


@pytest.mark.asyncio
async def test_robot_run_bridge_generates_tenant_safe_bounded_idempotency_key() -> None:
    run_service = FakeRobotRunService()
    bridge = RobotRunBridge(
        run_service=run_service,
        run_repository=FakeRobotRunRepository(()),
        tenant_id=ROBOT_TENANT_ID,
    )

    await bridge.respond_text(
        "测试语音",
        device_id="d" * 128,
        session_id="s" * 128,
        message_id="m" * 128,
    )

    idempotency_key = str(run_service.submitted["idempotency_key"])
    assert idempotency_key.startswith("robot:")
    assert len(idempotency_key) <= 64
    assert len(f"{ROBOT_TENANT_ID}:{idempotency_key}") <= 128


@pytest.mark.asyncio
async def test_robot_run_bridge_keys_distinguish_distinct_message_ids() -> None:
    run_service = FakeRobotRunService()
    bridge = RobotRunBridge(
        run_service=run_service,
        run_repository=FakeRobotRunRepository(()),
        tenant_id=ROBOT_TENANT_ID,
    )

    await bridge.respond_text(
        "同一句话",
        device_id="pi-lab-01",
        session_id="voice-session-1",
        message_id="robot-msg-1",
    )
    first_key = run_service.submitted["idempotency_key"]
    await bridge.respond_text(
        "同一句话",
        device_id="pi-lab-01",
        session_id="voice-session-1",
        message_id="robot-msg-1",
    )
    retry_key = run_service.submitted["idempotency_key"]
    await bridge.respond_text(
        "同一句话",
        device_id="pi-lab-01",
        session_id="voice-session-1",
        message_id="robot-msg-2",
    )
    next_key = run_service.submitted["idempotency_key"]

    assert retry_key == first_key
    assert next_key != first_key


def test_robot_websocket_returns_bounded_fallback_when_run_has_no_artifact() -> None:
    run_service = WaitingRobotRunService()
    run_repository = FakeRobotRunRepository(())
    client = _client(run_service=run_service, run_repository=run_repository)

    response = _final_speech_response(client)

    assert response["type"] == "assistant.text.done"
    assert "我已经收到你的语音" in response["payload"]["text"]
    assert str(ROBOT_RUN_ID) in response["payload"]["text"]


def test_robot_websocket_returns_bounded_fallback_when_bridge_fails() -> None:
    client = _client(
        run_service=FailingRobotRunService(),
        run_repository=FakeRobotRunRepository(()),
    )

    response = _final_speech_response(client)

    assert response["type"] == "assistant.text.done"
    assert "我已经收到你的语音" in response["payload"]["text"]


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


def test_robot_ota_manifest_rejects_invalid_current_version_without_500() -> None:
    client = _client()

    response = client.get(
        "/api/v1/robot/ota/manifest/pi-lab-01",
        headers=_device_headers(),
        params={"current_version": "probe", "protocol_version": "1"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation"


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
