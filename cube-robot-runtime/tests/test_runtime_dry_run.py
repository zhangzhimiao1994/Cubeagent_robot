import pytest
from cube_robot_runtime.main import RuntimeConfig, main, run_dry_run
from cube_robot_runtime.protocol.messages import RobotEnvelope


def test_dry_run_sends_heartbeat_and_utterance_to_mock_connection() -> None:
    result = run_dry_run(
        RuntimeConfig(
            server_url="mock://robot",
            device_id="pi-lab-01",
            session_id="voice-session-1",
        ),
        utterance="你好",
    )

    assert result.sent_types == ("device.heartbeat", "speech.partial")
    assert result.received_texts == ("我听到了：你好",)


def test_dry_run_uses_mock_connection_for_mock_urls() -> None:
    result = run_dry_run(
        RuntimeConfig(
            server_url="mock://robot",
            device_id="pi-lab-01",
        ),
        utterance="你好",
    )

    assert result.received_texts == ("我听到了：你好",)


class RecordingSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, raw: str) -> None:
        self.sent.append(raw)

    def recv(self) -> str:
        return RobotEnvelope.new(
            message_type="assistant.text.done",
            device_id="pi-lab-01",
            session_id="dry-run-session",
            payload={"text": "server-ok"},
        ).to_json()

    def close(self) -> None:
        return None


def test_runtime_dry_run_uses_real_websocket_for_ws_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    socket = RecordingSocket()

    def fake_create_connection(url: str, *, header: list[str], timeout: float) -> RecordingSocket:
        assert url == "ws://server/api/v1/robot/ws/pi-lab-01"
        assert header == ["X-Robot-Device-Token: robot-token"]
        assert timeout == 5.0
        return socket

    monkeypatch.setattr(
        "cube_robot_runtime.network.client.create_connection",
        fake_create_connection,
    )

    result = run_dry_run(
        RuntimeConfig(
            server_url="ws://server/api/v1/robot/ws/pi-lab-01",
            device_id="pi-lab-01",
            device_token="robot-token",
            timeout_seconds=5.0,
        ),
        "测试语音",
    )

    sent = [RobotEnvelope.from_json(raw) for raw in socket.sent]
    assert [message.type for message in sent] == ["device.heartbeat", "speech.partial"]
    assert sent[1].payload == {"text": "测试语音", "is_final": True}
    assert result.received_texts == ("server-ok",)


def test_dry_run_cli_prints_mock_response(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(
        [
            "dry-run",
            "--server-url",
            "mock://robot",
            "--device-id",
            "pi-lab-01",
            "--utterance",
            "你好",
        ]
    )

    assert exit_code == 0
    assert "我听到了：你好" in capsys.readouterr().out
