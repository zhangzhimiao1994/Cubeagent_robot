"""Audio playback backends for the Raspberry Pi runtime."""

import shutil
import signal
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from shlex import join
from typing import Protocol


class AudioPlayback(Protocol):
    def play_audio(self, codec: str, data: bytes) -> None: ...


@dataclass
class PlaybackRecorder:
    texts: list[str] = field(default_factory=list)
    audio: list[tuple[str, bytes]] = field(default_factory=list)

    def play(self, text: str) -> None:
        self.texts.append(text)

    def play_audio(self, codec: str, data: bytes) -> None:
        self.audio.append((codec, data))


@dataclass(frozen=True)
class CommandAudioPlayback:
    player: str | None = None
    timeout_seconds: float = 30.0

    def play_audio(self, codec: str, data: bytes) -> None:
        if not data:
            raise RuntimeError(f"audio playback received no data for codec {codec}")
        suffix = _suffix_for(codec)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
            temp_file.write(data)
            temp_path = Path(temp_file.name)
        command = self._command_for(codec, temp_path)
        try:
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=self.timeout_seconds,
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(_playback_error_message(exc, command)) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(_playback_timeout_message(exc, codec, len(data))) from exc
        except FileNotFoundError as exc:
            raise RuntimeError(f"audio playback command was not found: {command[0]}") from exc
        finally:
            temp_path.unlink(missing_ok=True)

    def _command_for(self, codec: str, media_path: Path) -> list[str]:
        selected = self.player or _default_player(codec)
        path = str(media_path)
        if selected in {"mpg123", "mpg321"}:
            return [selected, "-q", path]
        if selected == "mpv":
            return [selected, "--no-video", "--really-quiet", path]
        if selected == "aplay":
            return [selected, "-q", path]
        return [selected, path]


def _default_player(codec: str) -> str:
    candidates = ("mpg123", "mpg321", "mpv") if codec == "mp3" else ("aplay", "mpv")
    for candidate in candidates:
        if shutil.which(candidate):
            return candidate
    raise RuntimeError(f"no audio playback command found for codec {codec}")


def _suffix_for(codec: str) -> str:
    normalized = codec.lower().strip(".")
    return f".{normalized or 'audio'}"


def _playback_error_message(exc: subprocess.CalledProcessError, command: list[str]) -> str:
    stderr = _decode_output(exc.stderr)
    stdout = _decode_output(exc.output)
    details = stderr or stdout or "no output from playback command"
    status = _return_status(exc.returncode)
    return f"audio playback command failed with {status}: {details}. Command: {join(command)}."


def _playback_timeout_message(exc: subprocess.TimeoutExpired, codec: str, size_bytes: int) -> str:
    command = exc.cmd if isinstance(exc.cmd, list) else [str(exc.cmd)]
    return (
        f"audio playback command timed out after {exc.timeout:g} seconds "
        f"for codec {codec} ({size_bytes} bytes). Command: {join(command)}."
    )


def _return_status(returncode: int) -> str:
    if returncode < 0:
        signal_number = -returncode
        try:
            signal_name = signal.Signals(signal_number).name
        except ValueError:
            signal_name = f"signal {signal_number}"
        return f"{signal_name} ({signal_number})"
    return f"exit code {returncode}"


def _decode_output(output: bytes | str | None) -> str:
    if output is None:
        return ""
    if isinstance(output, str):
        return output.strip()
    return output.decode("utf-8", errors="replace").strip()
