"""Long-running listen loop for Raspberry Pi voice triggers."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Event

from cube_robot_runtime.audio.capture import AudioCapture, AudioCaptureConfig
from cube_robot_runtime.audio.vad import has_voice
from cube_robot_runtime.voice_once import VoiceOnceResult


@dataclass(frozen=True)
class ListenConfig:
    device_id: str
    probe: AudioCaptureConfig = field(default_factory=lambda: AudioCaptureConfig(duration_seconds=0.75))
    threshold: float = 0.02
    max_turns: int | None = None
    idle_sleep_seconds: float = 0.2
    cooldown_seconds: float = 0.75
    session_id_prefix: str = "listen"


@dataclass(frozen=True)
class ListenResult:
    probes: int
    triggered_turns: int


def run_listen_loop(
    config: ListenConfig,
    *,
    probe_capture: AudioCapture,
    run_turn: Callable[[str], VoiceOnceResult],
    stop_event: Event | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> ListenResult:
    if not config.device_id:
        raise ValueError("device_id must be non-empty")
    if config.threshold <= 0:
        raise ValueError("threshold must be positive")
    if config.max_turns is not None and config.max_turns <= 0:
        raise ValueError("max_turns must be positive when set")
    if config.idle_sleep_seconds < 0:
        raise ValueError("idle_sleep_seconds must not be negative")
    if config.cooldown_seconds < 0:
        raise ValueError("cooldown_seconds must not be negative")
    if not config.session_id_prefix:
        raise ValueError("session_id_prefix must be non-empty")

    stop = stop_event or Event()
    probes = 0
    triggered_turns = 0
    while not stop.is_set():
        if config.max_turns is not None and triggered_turns >= config.max_turns:
            break
        probe_audio = probe_capture.record()
        probes += 1
        if has_voice(probe_audio, threshold=config.threshold):
            triggered_turns += 1
            run_turn(f"{config.session_id_prefix}-{triggered_turns}")
            if config.cooldown_seconds:
                sleep(config.cooldown_seconds)
            continue
        if config.idle_sleep_seconds:
            sleep(config.idle_sleep_seconds)
    return ListenResult(probes=probes, triggered_turns=triggered_turns)
