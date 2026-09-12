"""Audio capture backends for the Raspberry Pi runtime."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from math import ceil
from typing import Protocol


class AudioCapture(Protocol):
    def record(self) -> bytes: ...


@dataclass(frozen=True)
class AudioCaptureConfig:
    codec: str = "wav"
    sample_rate_hz: int = 16000
    channels: int = 1
    duration_seconds: float = 4.0
    device: str | None = None


@dataclass(frozen=True)
class CommandAudioCapture:
    config: AudioCaptureConfig
    timeout_padding_seconds: float = 5.0

    def record(self) -> bytes:
        if self.config.codec != "wav":
            raise ValueError("command capture currently supports wav codec")
        duration = max(1, ceil(self.config.duration_seconds))
        command = [
            "arecord",
            "-q",
            "-f",
            "S16_LE",
            "-r",
            str(self.config.sample_rate_hz),
            "-c",
            str(self.config.channels),
            "-d",
            str(duration),
            "-t",
            "wav",
            "-",
        ]
        if self.config.device:
            command[1:1] = ["-D", self.config.device]
        result = subprocess.run(
            command,
            check=True,
            input=b"",
            capture_output=True,
            timeout=duration + self.timeout_padding_seconds,
        )
        if not result.stdout:
            raise RuntimeError("audio capture returned no data")
        return result.stdout
