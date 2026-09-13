import subprocess
from pathlib import Path

import pytest
from cube_robot_runtime.audio.playback import CommandAudioPlayback


def test_command_playback_uses_temp_file_for_mpg123(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_command: list[str] = []
    captured_payload = b""

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        nonlocal captured_payload
        captured_command.extend(command)
        assert kwargs.get("input") is None
        media_path = Path(command[-1])
        captured_payload = media_path.read_bytes()
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("cube_robot_runtime.audio.playback.subprocess.run", fake_run)

    CommandAudioPlayback(player="mpg123").play_audio("mp3", b"mp3-bytes")

    assert captured_command[:2] == ["mpg123", "-q"]
    assert captured_command[-1] != "-"
    assert captured_command[-1].endswith(".mp3")
    assert captured_payload == b"mp3-bytes"
    assert not Path(captured_command[-1]).exists()


def test_command_playback_reports_player_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.CalledProcessError(
            returncode=-11,
            cmd=command,
            stderr=b"decoder crashed\n",
        )

    monkeypatch.setattr("cube_robot_runtime.audio.playback.subprocess.run", fake_run)

    with pytest.raises(RuntimeError) as exc_info:
        CommandAudioPlayback(player="mpg123").play_audio("mp3", b"mp3-bytes")

    message = str(exc_info.value)
    assert "audio playback command failed" in message
    assert "SIGSEGV" in message
    assert "decoder crashed" in message
    assert "mpg123 -q" in message


def test_command_playback_rejects_empty_audio() -> None:
    with pytest.raises(RuntimeError, match="audio playback received no data for codec mp3"):
        CommandAudioPlayback(player="mpg123").play_audio("mp3", b"")


def test_command_playback_reports_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired(command, timeout=kwargs["timeout"])

    monkeypatch.setattr("cube_robot_runtime.audio.playback.subprocess.run", fake_run)

    with pytest.raises(RuntimeError) as exc_info:
        CommandAudioPlayback(player="mpg123", timeout_seconds=1).play_audio("mp3", b"mp3-bytes")

    message = str(exc_info.value)
    assert "audio playback command timed out after 1 seconds" in message
    assert "codec mp3" in message
    assert "9 bytes" in message
