"""Audio playback backends for the Raspberry Pi runtime."""

import shutil
import subprocess
from dataclasses import dataclass, field
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
        command = self._command_for(codec)
        subprocess.run(
            command,
            check=True,
            input=data,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=self.timeout_seconds,
        )

    def _command_for(self, codec: str) -> list[str]:
        selected = self.player or _default_player(codec)
        if selected in {"mpg123", "mpg321"}:
            return [selected, "-q", "-"]
        if selected == "mpv":
            return [selected, "--no-video", "--really-quiet", "-"]
        if selected == "aplay":
            return [selected, "-q", "-"]
        return [selected, "-"]


def _default_player(codec: str) -> str:
    candidates = ("mpg123", "mpg321", "mpv") if codec == "mp3" else ("aplay", "mpv")
    for candidate in candidates:
        if shutil.which(candidate):
            return candidate
    raise RuntimeError(f"no audio playback command found for codec {codec}")
