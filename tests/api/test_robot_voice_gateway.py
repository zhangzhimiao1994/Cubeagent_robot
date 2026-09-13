import logging
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.websockets import WebSocketDisconnect

from agent_hub.api.routers.admin import InMemoryAdminResourceService
from agent_hub.app import create_app
from agent_hub.auth.models import AuthenticatedPrincipal, InvalidCredentials, Role
from agent_hub.domain.runs import RunStatus, TaskMode
from agent_hub.robot.auth import RobotDeviceTokenStore
from agent_hub.robot.protocol import RobotMessageType, build_envelope
from agent_hub.runs.service import SubmittedRun
from agent_hub.settings import Settings, get_settings
from agent_hub.voice.companion import RobotRunBridge
from agent_hub.voice.gateway import create_robot_voice_router
from agent_hub.voice.media import SpeechTranscript, SynthesizedAudio, VoiceMediaService
from agent_hub.voice.minimax import MiniMaxSpeechConfig

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
    admin_resource_service: object | None = None,
    settings: Settings | None = None,
    base_url: str = "http://testserver",
) -> TestClient:
    app_kwargs: dict[str, object] = {
        "auth_service": StubAuthService(),
        "settings": settings
        or Settings(robot_device_tokens=SecretStr("pi-lab-01:robot-token")),
    }
    if run_service is not None:
        app_kwargs["run_service"] = run_service
    if run_repository is not None:
        app_kwargs["run_repository"] = run_repository
    if admin_resource_service is not None:
        app_kwargs["admin_resource_service"] = admin_resource_service
    return TestClient(
        create_app(**app_kwargs),
        base_url=base_url,
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


class FakeVoiceMediaService:
    def __init__(self) -> None:
        self.received_types: list[RobotMessageType] = []

    async def handle(self, envelope):
        self.received_types.append(envelope.type)
        if envelope.type is not RobotMessageType.AUDIO_END:
            return ()
        return (
            build_envelope(
                message_type=RobotMessageType.ASSISTANT_TEXT_DONE,
                device_id=envelope.device_id,
                session_id=envelope.session_id,
                payload={"text": "服务端回答"},
            ),
            build_envelope(
                message_type=RobotMessageType.TTS_AUDIO_CHUNK,
                device_id=envelope.device_id,
                session_id=envelope.session_id,
                payload={"codec": "mp3", "sequence": 1, "chunk_b64": "bXAz"},
            ),
            build_envelope(
                message_type=RobotMessageType.TTS_AUDIO_DONE,
                device_id=envelope.device_id,
                session_id=envelope.session_id,
                payload={"codec": "mp3", "total_chunks": 1},
            ),
        )


class FakeRobotRunRepository:
    def __init__(
        self,
        artifacts: tuple[dict[str, object], ...],
        events: tuple[dict[str, object], ...] = (),
    ) -> None:
        self._artifacts = artifacts
        self._events = events
        self.artifact_calls: list[tuple[UUID, UUID]] = []
        self.event_calls: list[tuple[UUID, UUID]] = []

    async def artifacts(self, tenant_id: UUID, run_id: UUID) -> tuple[dict[str, object], ...]:
        self.artifact_calls.append((tenant_id, run_id))
        return self._artifacts

    async def events(self, tenant_id: UUID, run_id: UUID) -> tuple[dict[str, object], ...]:
        self.event_calls.append((tenant_id, run_id))
        return self._events


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


def test_robot_websocket_routes_audio_turn_through_media_service() -> None:
    media_service = FakeVoiceMediaService()
    app = FastAPI()
    app.include_router(
        create_robot_voice_router(
            device_tokens=RobotDeviceTokenStore.from_secret(
                SecretStr("pi-lab-01:robot-token")
            ),
            media_service=media_service,
        )
    )
    client = TestClient(app)

    with client.websocket_connect("/api/v1/robot/ws/pi-lab-01", headers=_device_headers()) as ws:
        for message_type, payload in (
            (
                RobotMessageType.AUDIO_START,
                {"codec": "wav", "sample_rate_hz": 16000, "channels": 1},
            ),
            (
                RobotMessageType.AUDIO_CHUNK,
                {"codec": "wav", "sample_rate_hz": 16000, "sequence": 1, "chunk_b64": "QUJD"},
            ),
            (RobotMessageType.AUDIO_END, {"total_chunks": 1}),
        ):
            ws.send_json(
                build_envelope(
                    message_type=message_type,
                    device_id="pi-lab-01",
                    session_id="voice-session-1",
                    payload=payload,
                ).model_dump(mode="json")
            )
        responses = [ws.receive_json(), ws.receive_json(), ws.receive_json()]

    assert media_service.received_types == [
        RobotMessageType.AUDIO_START,
        RobotMessageType.AUDIO_CHUNK,
        RobotMessageType.AUDIO_END,
    ]
    assert [response["type"] for response in responses] == [
        "assistant.text.done",
        "tts.audio.chunk",
        "tts.audio.done",
    ]


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
    assert submitted["mode"].value == "direct"
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


def test_robot_websocket_reports_runtime_not_configured_when_run_fails_without_artifact() -> None:
    run_service = WaitingRobotRunService()
    run_repository = FakeRobotRunRepository(
        (),
        events=(
            {
                "type": "runtime.failed",
                "reason": "runtime_not_configured",
                "payload": {"error": {"code": "runtime.not_configured"}},
            },
        ),
    )
    client = _client(run_service=run_service, run_repository=run_repository)

    response = _final_speech_response(client)

    assert response["type"] == "assistant.text.done"
    assert "服务端 Agent 模型还没有配置" in response["payload"]["text"]
    assert str(ROBOT_RUN_ID) in response["payload"]["text"]


@pytest.mark.asyncio
async def test_robot_run_bridge_logs_fallback_without_raw_utterance(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="agent_hub.voice.companion")
    bridge = RobotRunBridge(
        run_service=WaitingRobotRunService(),
        run_repository=FakeRobotRunRepository(()),
        tenant_id=ROBOT_TENANT_ID,
    )

    response = await bridge.respond_text(
        "这是一段不应该默认写入日志的语音",
        device_id="pi-lab-01",
        session_id="voice-session-1",
    )

    assert "我已经收到你的语音" in response
    assert "robot_voice_fallback" in caplog.text
    assert "reason=run_artifact_missing" in caplog.text
    assert str(ROBOT_RUN_ID) in caplog.text
    assert "不应该默认写入日志" not in caplog.text


@pytest.mark.asyncio
async def test_robot_run_bridge_debug_logs_include_utterance_and_artifact_preview(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="agent_hub.voice.companion")
    bridge = RobotRunBridge(
        run_service=FakeRobotRunService(),
        run_repository=FakeRobotRunRepository(
            ({"content": {"text": "服务端 Agent 回复详情"}},)
        ),
        tenant_id=ROBOT_TENANT_ID,
        debug_voice_logs=True,
    )

    response = await bridge.respond_text(
        "帮我测试语音交互",
        device_id="pi-lab-01",
        session_id="voice-session-1",
    )

    assert response == "服务端 Agent 回复详情"
    assert "robot_voice_run_submit" in caplog.text
    assert "utterance_preview=帮我测试语音交互" in caplog.text
    assert "robot_voice_run_artifact_selected" in caplog.text
    assert "response_preview=服务端 Agent 回复详情" in caplog.text


@pytest.mark.asyncio
async def test_voice_media_debug_logs_asr_and_tts_without_audio_chunks(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="agent_hub.voice.media")

    class FakeSpeechProvider:
        async def transcribe(self, _audio: object) -> SpeechTranscript:
            return SpeechTranscript(text="识别出来的用户语音", confidence=0.91)

        async def synthesize(self, text: str, _options: object) -> SynthesizedAudio:
            assert text == "准备播放的回复"
            return SynthesizedAudio(codec="mp3", data=b"mp3", sample_rate_hz=32000)

    async def responder(envelope):
        return (
            build_envelope(
                message_type=RobotMessageType.ASSISTANT_TEXT_DONE,
                device_id=envelope.device_id,
                session_id=envelope.session_id,
                payload={"text": "准备播放的回复"},
            ),
        )

    service = VoiceMediaService(
        stt_provider=FakeSpeechProvider(),
        tts_provider=FakeSpeechProvider(),
        responder=responder,
        debug_voice_logs=True,
    )

    start = build_envelope(
        message_type=RobotMessageType.AUDIO_START,
        device_id="pi-lab-01",
        session_id="voice-session-1",
        payload={"codec": "wav", "sample_rate_hz": 16000},
    )
    chunk = build_envelope(
        message_type=RobotMessageType.AUDIO_CHUNK,
        device_id="pi-lab-01",
        session_id="voice-session-1",
        payload={"sequence": 1, "chunk_b64": "QUJD"},
    )
    done = build_envelope(
        message_type=RobotMessageType.AUDIO_END,
        device_id="pi-lab-01",
        session_id="voice-session-1",
        payload={"total_chunks": 1},
    )

    assert await service.handle(start) == ()
    assert await service.handle(chunk) == ()
    responses = await service.handle(done)

    assert [response.type for response in responses] == [
        RobotMessageType.SPEECH_PARTIAL,
        RobotMessageType.ASSISTANT_TEXT_DONE,
        RobotMessageType.TTS_AUDIO_CHUNK,
        RobotMessageType.TTS_AUDIO_DONE,
    ]
    assert "robot_voice_asr_done" in caplog.text
    assert "asr_text_preview=识别出来的用户语音" in caplog.text
    assert "robot_voice_tts_start" in caplog.text
    assert "assistant_text_preview=准备播放的回复" in caplog.text
    assert "QUJD" not in caplog.text


def test_robot_websocket_returns_bounded_fallback_when_bridge_fails() -> None:
    client = _client(
        run_service=FailingRobotRunService(),
        run_repository=FakeRobotRunRepository(()),
    )

    response = _final_speech_response(client)

    assert response["type"] == "assistant.text.done"
    assert "我已经收到你的语音" in response["payload"]["text"]


@pytest.mark.asyncio
async def test_voice_media_ignores_transcript_without_required_wake_word(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="agent_hub.voice.media")
    responder_calls = 0

    class FakeSpeechProvider:
        async def transcribe(self, _audio: object) -> SpeechTranscript:
            return SpeechTranscript(text="今天北京天气怎么样", confidence=0.9)

        async def synthesize(self, _text: str, _options: object) -> SynthesizedAudio:
            raise AssertionError("TTS should not run without the wake word")

    async def responder(_envelope):
        nonlocal responder_calls
        responder_calls += 1
        return ()

    service = VoiceMediaService(
        stt_provider=FakeSpeechProvider(),
        tts_provider=FakeSpeechProvider(),
        responder=responder,
        wake_word_required=True,
        wake_words=("小立方",),
    )

    start = build_envelope(
        message_type=RobotMessageType.AUDIO_START,
        device_id="pi-lab-01",
        session_id="voice-session-1",
        payload={"codec": "wav", "sample_rate_hz": 16000},
    )
    chunk = build_envelope(
        message_type=RobotMessageType.AUDIO_CHUNK,
        device_id="pi-lab-01",
        session_id="voice-session-1",
        payload={"sequence": 1, "chunk_b64": "QUJD"},
    )
    done = build_envelope(
        message_type=RobotMessageType.AUDIO_END,
        device_id="pi-lab-01",
        session_id="voice-session-1",
        payload={"total_chunks": 1},
    )

    assert await service.handle(start) == ()
    assert await service.handle(chunk) == ()
    responses = await service.handle(done)

    assert [response.type for response in responses] == [RobotMessageType.SPEECH_PARTIAL]
    assert responder_calls == 0
    assert "robot_voice_wake_word_ignored" in caplog.text


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


def test_robot_ota_upload_release_becomes_device_manifest(tmp_path) -> None:  # type: ignore[no-untyped-def]
    admin_service = InMemoryAdminResourceService()
    client = _client(
        admin_resource_service=admin_service,
        settings=Settings(
            robot_device_tokens=SecretStr("pi-lab-01:robot-token"),
            generated_artifact_dir=tmp_path,
        ),
        base_url="https://testserver",
    )

    upload = client.post(
        "/api/v1/admin/robot/ota/releases/upload",
        headers=_headers(),
        data={
            "version": "2026.09.13+1",
            "channel": "stable",
            "min_protocol_version": "1",
            "activate": "true",
        },
        files={"artifact": ("cube-robot-runtime.tar.gz", b"runtime-bytes", "application/gzip")},
    )

    assert upload.status_code == 201
    release = upload.json()
    assert release["version"] == "2026.09.13+1"
    assert release["active"] is True
    assert release["artifact_size_bytes"] == len(b"runtime-bytes")
    assert release["artifact_sha256"] == (
        "99235f1c93582c5d7f669de64945af872b90a47e628250eda09a318dcbffeec7"
    )
    assert release["artifact_url"].startswith(
        "https://testserver/api/v1/robot/ota/artifacts/{device_id}/2026.09.13+1/"
    )

    manifest = client.get(
        "/api/v1/robot/ota/manifest/pi-lab-01",
        headers=_device_headers(),
        params={"current_version": "2026.09.10+0", "protocol_version": "1"},
    )

    assert manifest.status_code == 200
    body = manifest.json()
    assert body["decision"]["status"] == "update_available"
    assert body["manifest"]["version"] == "2026.09.13+1"
    assert body["manifest"]["artifact"]["sha256"] == release["artifact_sha256"]
    assert body["manifest"]["artifact"]["url"].startswith(
        "https://testserver/api/v1/robot/ota/artifacts/pi-lab-01/2026.09.13+1/"
    )

    artifact = client.get(body["manifest"]["artifact"]["url"], headers=_device_headers())

    assert artifact.status_code == 200
    assert artifact.content == b"runtime-bytes"


def test_robot_ota_upload_generates_https_artifact_url_from_http_console(tmp_path) -> None:  # type: ignore[no-untyped-def]
    admin_service = InMemoryAdminResourceService()
    client = _client(
        admin_resource_service=admin_service,
        settings=Settings(
            robot_device_tokens=SecretStr("pi-lab-01:robot-token"),
            generated_artifact_dir=tmp_path,
        ),
        base_url="http://testserver",
    )

    upload = client.post(
        "/api/v1/admin/robot/ota/releases/upload",
        headers=_headers(),
        data={
            "version": "2026.09.13+2",
            "channel": "stable",
            "min_protocol_version": "1",
            "activate": "true",
        },
        files={"artifact": ("cube-robot-runtime.tar.gz", b"runtime-bytes", "application/gzip")},
    )

    assert upload.status_code == 201
    assert upload.json()["artifact_url"].startswith("https://testserver/")


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


def test_app_lifespan_reconfigures_logging_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    levels: list[object] = []

    def fake_configure_logging(*, level: object, stream: object | None = None) -> None:
        del stream
        levels.append(level)

    monkeypatch.setenv("AGENT_HUB_LOG_LEVEL", "INFO")
    monkeypatch.setenv("AGENT_HUB_ROBOT_DEVICE_TOKENS", "pi-lab-01:robot-token")
    get_settings.cache_clear()
    monkeypatch.setattr("agent_hub.app.configure_logging", fake_configure_logging)

    app = create_app(
        auth_service=StubAuthService(),
        config_service=object(),
        admin_resource_service=object(),
        user_admin_service=object(),
        run_service=FakeRobotRunService(),
        run_repository=FakeRobotRunRepository(()),
        rate_limiter=object(),
        redis_probe=lambda: None,
        database_probe=lambda: None,
    )
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200

    assert levels[0] == "WARNING"
    assert "INFO" in levels
    get_settings.cache_clear()


def test_robot_websocket_uses_minimax_media_provider_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeMiniMaxSpeechClient:
        def __init__(self, config: object) -> None:
            self.config = config

        async def transcribe(self, _audio: object) -> SpeechTranscript:
            return SpeechTranscript(text="识别文本")

        async def synthesize(self, _text: str, _options: object) -> SynthesizedAudio:
            return SynthesizedAudio(codec="mp3", data=b"mp3", sample_rate_hz=32000)

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr("agent_hub.app.MiniMaxSpeechClient", FakeMiniMaxSpeechClient)
    client = TestClient(
        create_app(
            settings=Settings(
                robot_device_tokens=SecretStr("pi-lab-01:robot-token"),
                robot_voice_media_provider="minimax",
                minimax_api_key=SecretStr("secret"),
                minimax_tts_voice_id="robot-voice",
            )
        )
    )

    with client.websocket_connect("/api/v1/robot/ws/pi-lab-01", headers=_device_headers()) as ws:
        for message_type, payload in (
            (
                RobotMessageType.AUDIO_START,
                {"codec": "wav", "sample_rate_hz": 16000, "channels": 1},
            ),
            (
                RobotMessageType.AUDIO_CHUNK,
                {"codec": "wav", "sample_rate_hz": 16000, "sequence": 1, "chunk_b64": "QUJD"},
            ),
            (RobotMessageType.AUDIO_END, {"total_chunks": 1}),
        ):
            ws.send_json(
                build_envelope(
                    message_type=message_type,
                    device_id="pi-lab-01",
                    session_id="voice-session-1",
                    payload=payload,
                ).model_dump(mode="json")
            )
        responses = [
            ws.receive_json(),
            ws.receive_json(),
            ws.receive_json(),
            ws.receive_json(),
            ws.receive_json(),
        ]

    assert [response["type"] for response in responses] == [
        "speech.partial",
        "assistant.text.done",
        "conversation.end",
        "tts.audio.chunk",
        "tts.audio.done",
    ]
    assert responses[0]["payload"]["text"] == "识别文本"
    assert responses[3]["payload"]["chunk_b64"] == "bXAz"


def test_robot_websocket_uses_robot_voice_settings_saved_from_console(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_configs: list[MiniMaxSpeechConfig] = []

    class FakeMiniMaxSpeechClient:
        def __init__(self, config: MiniMaxSpeechConfig) -> None:
            self.config = config
            created_configs.append(config)

        async def transcribe(self, _audio: object) -> SpeechTranscript:
            return SpeechTranscript(text="控制台语音")

        async def synthesize(self, _text: str, _options: object) -> SynthesizedAudio:
            return SynthesizedAudio(codec="mp3", data=b"console-mp3", sample_rate_hz=32000)

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr("agent_hub.app.MiniMaxSpeechClient", FakeMiniMaxSpeechClient)
    service = InMemoryAdminResourceService()
    client = _client(admin_resource_service=service)
    payload = client.get("/api/v1/admin/settings", headers=_headers()).json()
    payload["robot_voice"] = {
        **payload["robot_voice"],
        "enabled": True,
        "media_provider": "minimax",
        "minimax_api_key": "console-minimax-key",
        "minimax_tts_model": "speech-2.8-hd",
        "minimax_tts_voice_id": "console-voice",
        "default_voice_id": "console-voice",
        "voices": [
            {
                "id": "console-voice",
                "name": "控制台音色",
                "provider": "minimax",
                "voice_id": "console-voice",
                "enabled": True,
                "cloned": False,
            }
        ],
    }

    assert client.put("/api/v1/admin/settings", headers=_headers(), json=payload).status_code == 200

    with client.websocket_connect("/api/v1/robot/ws/pi-lab-01", headers=_device_headers()) as ws:
        for message_type, body in (
            (
                RobotMessageType.AUDIO_START,
                {"codec": "wav", "sample_rate_hz": 16000, "channels": 1},
            ),
            (
                RobotMessageType.AUDIO_CHUNK,
                {"codec": "wav", "sample_rate_hz": 16000, "sequence": 1, "chunk_b64": "QUJD"},
            ),
            (RobotMessageType.AUDIO_END, {"total_chunks": 1}),
        ):
            ws.send_json(
                build_envelope(
                    message_type=message_type,
                    device_id="pi-lab-01",
                    session_id="voice-session-1",
                    payload=body,
                ).model_dump(mode="json")
            )
        responses = [ws.receive_json() for _ in range(5)]

    assert responses[0]["payload"]["text"] == "控制台语音"
    assert responses[3]["payload"]["chunk_b64"] == "Y29uc29sZS1tcDM="
    assert created_configs[0].api_key == "console-minimax-key"
    assert created_configs[0].tts_model == "speech-2.8-hd"
    assert created_configs[0].default_voice_id == "console-voice"
