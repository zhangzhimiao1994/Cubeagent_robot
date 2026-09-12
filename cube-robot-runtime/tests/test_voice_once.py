import base64
import json
from pathlib import Path

from cube_robot_runtime.audio.capture import AudioCaptureConfig
from cube_robot_runtime.audio.playback import PlaybackRecorder
from cube_robot_runtime.main import load_runtime_config, main
from cube_robot_runtime.protocol.messages import RobotEnvelope
from cube_robot_runtime.voice_once import VoiceOnceConfig, run_voice_once


class FakeCapture:
    def __init__(self, data: bytes = b"abcdef") -> None:
        self.data = data

    def record(self) -> bytes:
        return self.data


class ScriptedConnection:
    def __init__(self) -> None:
        self.sent: list[RobotEnvelope] = []
        self.closed = False
        self.responses = [
            RobotEnvelope.new(
                message_type="speech.partial",
                device_id="pi-lab-01",
                session_id="voice-session-1",
                payload={"text": "你好", "is_final": True},
            ),
            RobotEnvelope.new(
                message_type="assistant.text.done",
                device_id="pi-lab-01",
                session_id="voice-session-1",
                payload={"text": "服务端回答"},
            ),
            RobotEnvelope.new(
                message_type="tts.audio.chunk",
                device_id="pi-lab-01",
                session_id="voice-session-1",
                payload={
                    "codec": "mp3",
                    "sequence": 1,
                    "chunk_b64": base64.b64encode(b"mp3").decode("ascii"),
                },
            ),
            RobotEnvelope.new(
                message_type="tts.audio.done",
                device_id="pi-lab-01",
                session_id="voice-session-1",
                payload={"codec": "mp3", "total_chunks": 1},
            ),
        ]

    def send(self, envelope: RobotEnvelope) -> None:
        self.sent.append(envelope)

    def receive(self) -> RobotEnvelope:
        return self.responses.pop(0)

    def close(self) -> None:
        self.closed = True


def test_voice_once_sends_audio_turn_and_plays_tts(monkeypatch) -> None:
    connection = ScriptedConnection()

    def fake_open_connection(
        server_url: str,
        *,
        device_token: str | None,
        timeout_seconds: float,
    ) -> ScriptedConnection:
        assert server_url == "ws://server/api/v1/robot/ws/pi-lab-01"
        assert device_token == "robot-token"
        assert timeout_seconds == 5.0
        return connection

    monkeypatch.setattr("cube_robot_runtime.voice_once.open_connection", fake_open_connection)
    playback = PlaybackRecorder()

    result = run_voice_once(
        VoiceOnceConfig(
            server_url="ws://server/api/v1/robot/ws/pi-lab-01",
            device_id="pi-lab-01",
            session_id="voice-session-1",
            device_token="robot-token",
            timeout_seconds=5.0,
            voice_id="robot-voice",
            tts_model="speech-2.8-turbo",
            capture=AudioCaptureConfig(duration_seconds=1),
            chunk_size_bytes=3,
        ),
        capture=FakeCapture(),
        playback=playback,
    )

    assert [envelope.type for envelope in connection.sent] == [
        "device.heartbeat",
        "audio.start",
        "audio.chunk",
        "audio.chunk",
        "audio.end",
    ]
    assert connection.sent[1].payload == {
        "codec": "wav",
        "sample_rate_hz": 16000,
        "channels": 1,
        "language": "zh",
        "voice_id": "robot-voice",
        "tts_model": "speech-2.8-turbo",
    }
    assert connection.sent[2].payload["chunk_b64"] == base64.b64encode(b"abc").decode("ascii")
    assert connection.sent[3].payload["chunk_b64"] == base64.b64encode(b"def").decode("ascii")
    assert connection.sent[4].payload == {"total_chunks": 2}
    assert result.sent_types == (
        "device.heartbeat",
        "audio.start",
        "audio.chunk",
        "audio.chunk",
        "audio.end",
    )
    assert result.received_types == (
        "speech.partial",
        "assistant.text.done",
        "tts.audio.chunk",
        "tts.audio.done",
    )
    assert result.received_texts == ("服务端回答",)
    assert result.played_audio_codecs == ("mp3",)
    assert playback.audio == [("mp3", b"mp3")]
    assert connection.closed is True


def test_runtime_config_loads_voice_and_audio_options(tmp_path: Path) -> None:
    config = tmp_path / "robot.toml"
    config.write_text(
        """
[runtime]
device_id = 'pi-lab-01'
server_url = 'ws://server/api/v1/robot/ws/pi-lab-01'
device_token = 'robot-token'
language = 'zh'
voice_id = 'robot-voice'
tts_model = 'speech-2.8-turbo'

[audio]
codec = 'wav'
sample_rate_hz = 16000
channels = 1
duration_seconds = 2.0
device = 'plughw:1,0'
""",
        encoding="utf-8",
    )

    loaded = load_runtime_config(config)

    assert loaded.voice_id == "robot-voice"
    assert loaded.tts_model == "speech-2.8-turbo"
    assert loaded.capture.device == "plughw:1,0"
    assert loaded.capture.duration_seconds == 2.0


def test_voice_once_cli_prints_summary(monkeypatch, tmp_path: Path, capsys) -> None:
    config = tmp_path / "robot.toml"
    config.write_text(
        "[runtime]\ndevice_id = 'pi-lab-01'\nserver_url = 'mock://robot'\n",
        encoding="utf-8",
    )

    class FakeCommandCapture:
        def __init__(self, _config: object) -> None:
            return None

        def record(self) -> bytes:
            return b"audio"

    class FakeCommandPlayback(PlaybackRecorder):
        def __init__(self, player: str | None = None) -> None:
            super().__init__()
            self.player = player

    connection = ScriptedConnection()
    monkeypatch.setattr("cube_robot_runtime.main.CommandAudioCapture", FakeCommandCapture)
    monkeypatch.setattr("cube_robot_runtime.main.CommandAudioPlayback", FakeCommandPlayback)
    monkeypatch.setattr(
        "cube_robot_runtime.voice_once.open_connection",
        lambda *_args, **_kwargs: connection,
    )

    exit_code = main(["voice-once", "--config", str(config), "--session-id", "voice-session-1"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["sent_types"] == [
        "device.heartbeat",
        "audio.start",
        "audio.chunk",
        "audio.end",
    ]
    assert output["played_audio_codecs"] == ["mp3"]
