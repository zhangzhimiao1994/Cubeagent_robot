import io
import json
import wave
from pathlib import Path

from cube_robot_runtime.audio.capture import AudioCaptureConfig
from cube_robot_runtime.audio.vad import has_voice
from cube_robot_runtime.listen import ListenConfig, run_listen_loop
from cube_robot_runtime.main import load_runtime_config, main
from cube_robot_runtime.voice_once import VoiceOnceResult


def wav_bytes(samples: list[int]) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"".join(sample.to_bytes(2, "little", signed=True) for sample in samples))
    return output.getvalue()


def test_vad_detects_loud_wav_and_rejects_silence() -> None:
    assert has_voice(wav_bytes([0] * 1600), threshold=0.02) is False
    assert has_voice(wav_bytes([6000, -6000] * 800), threshold=0.02) is True


class ProbeCapture:
    def __init__(self, probes: list[bytes]) -> None:
        self.probes = probes

    def record(self) -> bytes:
        return self.probes.pop(0)


def test_listen_loop_waits_for_voice_then_runs_one_turn() -> None:
    turns: list[str] = []
    sleeps: list[float] = []
    probe = ProbeCapture(
        [
            wav_bytes([0] * 1600),
            wav_bytes([6000, -6000] * 800),
        ]
    )

    def run_turn(session_id: str) -> VoiceOnceResult:
        turns.append(session_id)
        return VoiceOnceResult(
            sent_types=("device.heartbeat", "audio.start", "audio.end"),
            received_types=("assistant.text.done",),
            received_texts=("收到",),
            played_audio_codecs=("mp3",),
        )

    result = run_listen_loop(
        ListenConfig(
            device_id="pi-lab-01",
            probe=AudioCaptureConfig(duration_seconds=0.25),
            threshold=0.02,
            max_turns=1,
            idle_sleep_seconds=0,
            cooldown_seconds=0.5,
            session_id_prefix="voice",
        ),
        probe_capture=probe,
        run_turn=run_turn,
        sleep=sleeps.append,
    )

    assert result.probes == 2
    assert result.triggered_turns == 1
    assert turns == ["voice-1"]
    assert sleeps == [0.5]


def test_runtime_config_loads_listen_options(tmp_path: Path) -> None:
    config = tmp_path / "robot.toml"
    config.write_text(
        """
[runtime]
device_id = 'pi-lab-01'
server_url = 'ws://server/api/v1/robot/ws/pi-lab-01'

[listen]
probe_duration_seconds = 1.5
voice_threshold = 0.04
idle_sleep_seconds = 0.1
cooldown_seconds = 1.25
session_id_prefix = 'robot-talk'
""",
        encoding="utf-8",
    )

    loaded = load_runtime_config(config)

    assert loaded.listen_probe_duration_seconds == 1.5
    assert loaded.listen_voice_threshold == 0.04
    assert loaded.listen_idle_sleep_seconds == 0.1
    assert loaded.listen_cooldown_seconds == 1.25
    assert loaded.listen_session_id_prefix == "robot-talk"


def test_listen_cli_prints_summary(monkeypatch, tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    config = tmp_path / "robot.toml"
    config.write_text(
        """
[runtime]
device_id = 'pi-lab-01'
server_url = 'mock://robot'

[listen]
voice_threshold = 0.03
idle_sleep_seconds = 0.1
cooldown_seconds = 1.0
session_id_prefix = 'lab'
""",
        encoding="utf-8",
    )
    listen_configs: list[ListenConfig] = []

    def fake_run_listen_loop(config: ListenConfig, **_kwargs: object) -> object:
        listen_configs.append(config)
        return object_with_summary()

    monkeypatch.setattr(
        "cube_robot_runtime.main.run_listen_loop",
        fake_run_listen_loop,
    )

    exit_code = main(
        [
            "listen",
            "--config",
            str(config),
            "--max-turns",
            "1",
            "--probe-duration-seconds",
            "0.25",
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {
        "probes": 2,
        "triggered_turns": 1,
    }
    assert listen_configs == [
        ListenConfig(
            device_id="pi-lab-01",
            probe=AudioCaptureConfig(duration_seconds=0.25),
            threshold=0.03,
            max_turns=1,
            idle_sleep_seconds=0.1,
            cooldown_seconds=1.0,
            session_id_prefix="lab",
        )
    ]


def test_systemd_service_starts_listen_mode() -> None:
    service = Path(__file__).parents[1] / "scripts" / "cube-robot.service"

    assert "run-runtime.sh listen --config /etc/cube-robot/robot.toml" in service.read_text(encoding="utf-8")


def object_with_summary() -> object:
    class Summary:
        probes = 2
        triggered_turns = 1

    return Summary()
