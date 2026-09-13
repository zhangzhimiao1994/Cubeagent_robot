import subprocess

import pytest
from cube_robot_runtime.audio.capture import AudioCaptureConfig, CommandAudioCapture


def test_command_capture_uses_configured_alsa_device(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_command: list[str] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        captured_command.extend(command)
        return subprocess.CompletedProcess(command, 0, stdout=b"wav-bytes", stderr=b"")

    monkeypatch.setattr("cube_robot_runtime.audio.capture.subprocess.run", fake_run)

    audio = CommandAudioCapture(AudioCaptureConfig(device="plughw:1,0")).record()

    assert audio == b"wav-bytes"
    assert captured_command[:3] == ["arecord", "-D", "plughw:1,0"]


def test_command_capture_reports_arecord_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=command,
            output=b"",
            stderr=b"arecord: main:831: audio open error: No such file or directory\n",
        )

    monkeypatch.setattr("cube_robot_runtime.audio.capture.subprocess.run", fake_run)

    with pytest.raises(RuntimeError) as exc_info:
        CommandAudioCapture(AudioCaptureConfig(device="plughw:1,0")).record()

    message = str(exc_info.value)
    assert "audio capture command failed with exit code 1" in message
    assert "audio open error" in message
    assert "plughw:1,0" in message
    assert "arecord -D plughw:1,0" in message
    assert "[audio].device" in message


def test_command_capture_rejects_empty_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr("cube_robot_runtime.audio.capture.subprocess.run", fake_run)

    with pytest.raises(RuntimeError, match="audio capture returned no data"):
        CommandAudioCapture(AudioCaptureConfig()).record()
