"""Dry-run command for the standalone device runtime."""

import argparse
import json
import signal
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event

from cube_robot_runtime.audio.capture import AudioCaptureConfig, CommandAudioCapture
from cube_robot_runtime.audio.playback import CommandAudioPlayback, PlaybackRecorder
from cube_robot_runtime.device.identity import DeviceIdentity
from cube_robot_runtime.network.client import open_connection
from cube_robot_runtime.protocol.messages import RobotEnvelope
from cube_robot_runtime.voice_once import VoiceOnceConfig, run_voice_once


@dataclass(frozen=True)
class RuntimeConfig:
    server_url: str
    device_id: str
    session_id: str = "dry-run-session"
    device_token: str | None = None
    timeout_seconds: float = 10.0
    language: str | None = "zh"
    voice_id: str | None = None
    tts_model: str | None = None
    capture: AudioCaptureConfig = field(default_factory=AudioCaptureConfig)


@dataclass(frozen=True)
class DryRunResult:
    sent_types: tuple[str, ...]
    received_texts: tuple[str, ...]


def run_dry_run(config: RuntimeConfig, utterance: str) -> DryRunResult:
    identity = DeviceIdentity(device_id=config.device_id)
    connection = open_connection(
        config.server_url,
        device_token=config.device_token,
        timeout_seconds=config.timeout_seconds,
    )
    recorder = PlaybackRecorder()
    heartbeat = RobotEnvelope.new(
        message_type="device.heartbeat",
        device_id=identity.device_id,
        session_id=config.session_id,
        payload={"runtime_version": "0.1.0"},
    )
    utterance_message = RobotEnvelope.new(
        message_type="speech.partial",
        device_id=identity.device_id,
        session_id=config.session_id,
        payload={"text": utterance, "is_final": True},
    )
    sent = (heartbeat, utterance_message)
    try:
        for envelope in sent:
            connection.send(envelope)
        response = connection.receive()
        text = response.payload.get("text")
        if isinstance(text, str) and response.type == "assistant.text.done":
            recorder.play(text)
    finally:
        connection.close()
    return DryRunResult(
        sent_types=tuple(envelope.type for envelope in sent),
        received_texts=tuple(recorder.texts),
    )


def load_runtime_config(path: Path) -> RuntimeConfig:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    runtime = data.get("runtime")
    audio = data.get("audio", {})
    if not isinstance(runtime, dict):
        raise TypeError("config must contain a runtime table")
    if not isinstance(audio, dict):
        raise TypeError("config audio table must be an object when set")
    device_id = runtime.get("device_id")
    server_url = runtime.get("server_url")
    device_token = runtime.get("device_token")
    if not isinstance(device_id, str) or not device_id:
        raise ValueError("runtime.device_id must be a non-empty string")
    if not isinstance(server_url, str) or not server_url:
        raise ValueError("runtime.server_url must be a non-empty string")
    if device_token is not None and (not isinstance(device_token, str) or not device_token):
        raise ValueError("runtime.device_token must be a non-empty string when set")
    return RuntimeConfig(
        server_url=server_url,
        device_id=device_id,
        device_token=device_token if isinstance(device_token, str) else None,
        language=_optional_string(runtime, "language", default="zh"),
        voice_id=_optional_string(runtime, "voice_id"),
        tts_model=_optional_string(runtime, "tts_model"),
        capture=AudioCaptureConfig(
            codec=_optional_string(audio, "codec", default="wav") or "wav",
            sample_rate_hz=_optional_positive_int(audio, "sample_rate_hz", default=16000),
            channels=_optional_positive_int(audio, "channels", default=1),
            duration_seconds=_optional_positive_float(audio, "duration_seconds", default=4.0),
            device=_optional_string(audio, "device"),
        ),
    )


def run_runtime(config: RuntimeConfig, *, once: bool, stop_event: Event) -> int:
    while not stop_event.is_set():
        print(json.dumps({"type": "device.heartbeat", "device_id": config.device_id}))
        if once:
            return 0
        stop_event.wait(timeout=30)
    return 0


def _voice_once_config(config: RuntimeConfig, session_id: str) -> VoiceOnceConfig:
    return VoiceOnceConfig(
        server_url=config.server_url,
        device_id=config.device_id,
        session_id=session_id,
        device_token=config.device_token,
        timeout_seconds=config.timeout_seconds,
        language=config.language,
        voice_id=config.voice_id,
        tts_model=config.tts_model,
        capture=config.capture,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    dry_run = subcommands.add_parser("dry-run")
    dry_run.add_argument("--server-url", required=True)
    dry_run.add_argument("--device-id", required=True)
    dry_run.add_argument("--device-token")
    dry_run.add_argument("--session-id", default="dry-run-session")
    dry_run.add_argument("--timeout-seconds", type=float, default=10.0)
    dry_run.add_argument("--utterance", required=True)
    run = subcommands.add_parser("run")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--once", action="store_true")
    voice_once = subcommands.add_parser("voice-once")
    voice_once.add_argument("--config", type=Path, required=True)
    voice_once.add_argument("--session-id", default="voice-once-session")
    voice_once.add_argument("--player")
    args = parser.parse_args(argv)
    if args.command == "run":
        config = load_runtime_config(args.config)
        stop_event = Event()

        def request_stop(_signum: int, _frame: object) -> None:
            stop_event.set()

        handled_signals = (signal.SIGTERM, signal.SIGINT)
        previous_handlers = {signum: signal.signal(signum, request_stop) for signum in handled_signals}
        try:
            return run_runtime(config, once=args.once, stop_event=stop_event)
        except KeyboardInterrupt:
            return 0
        finally:
            for signum, previous_handler in previous_handlers.items():
                signal.signal(signum, previous_handler)
    if args.command == "voice-once":
        config = load_runtime_config(args.config)
        result = run_voice_once(
            _voice_once_config(config, args.session_id),
            capture=CommandAudioCapture(config.capture),
            playback=CommandAudioPlayback(player=args.player),
        )
        print(
            json.dumps(
                {
                    "sent_types": result.sent_types,
                    "received_types": result.received_types,
                    "received_texts": result.received_texts,
                    "played_audio_codecs": result.played_audio_codecs,
                },
                ensure_ascii=False,
            )
        )
        return 0
    result = run_dry_run(
        RuntimeConfig(
            args.server_url,
            args.device_id,
            args.session_id,
            args.device_token,
            args.timeout_seconds,
        ),
        args.utterance,
    )
    print(json.dumps({"sent_types": result.sent_types, "received_texts": result.received_texts}, ensure_ascii=False))
    return 0


def _optional_string(data: dict[str, object], key: str, *, default: str | None = None) -> str | None:
    value = data.get(key, default)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string when set")
    return value


def _optional_positive_int(data: dict[str, object], key: str, *, default: int) -> int:
    value = data.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{key} must be a positive integer")
    return value


def _optional_positive_float(data: dict[str, object], key: str, *, default: float) -> float:
    value = data.get(key, default)
    if not isinstance(value, int | float) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{key} must be a positive number")
    return float(value)


if __name__ == "__main__":
    raise SystemExit(main())
