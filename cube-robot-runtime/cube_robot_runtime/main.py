"""Dry-run command for the standalone device runtime."""

import argparse
import json
import signal
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from threading import Event

from cube_robot_runtime.audio.capture import AudioCaptureConfig, CommandAudioCapture
from cube_robot_runtime.audio.playback import CommandAudioPlayback, PlaybackRecorder
from cube_robot_runtime.device.identity import DeviceIdentity
from cube_robot_runtime.listen import ListenConfig, run_listen_loop
from cube_robot_runtime.network.client import open_connection
from cube_robot_runtime.ota.updater import apply_update, check_for_update
from cube_robot_runtime.policy import fetch_device_policy
from cube_robot_runtime.protocol.messages import RobotEnvelope
from cube_robot_runtime.voice_once import VoiceOnceConfig, VoiceOnceResult, run_voice_once


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
    listen_probe_duration_seconds: float = 0.75
    listen_voice_threshold: float = 0.02
    listen_idle_sleep_seconds: float = 0.2
    listen_cooldown_seconds: float = 0.75
    listen_session_id_prefix: str = "listen"


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
    listen = data.get("listen", {})
    if not isinstance(runtime, dict):
        raise TypeError("config must contain a runtime table")
    if not isinstance(audio, dict):
        raise TypeError("config audio table must be an object when set")
    if not isinstance(listen, dict):
        raise TypeError("config listen table must be an object when set")
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
        listen_probe_duration_seconds=_optional_positive_float(
            listen,
            "probe_duration_seconds",
            default=0.75,
        ),
        listen_voice_threshold=_optional_positive_float(listen, "voice_threshold", default=0.02),
        listen_idle_sleep_seconds=_optional_non_negative_float(listen, "idle_sleep_seconds", default=0.2),
        listen_cooldown_seconds=_optional_non_negative_float(listen, "cooldown_seconds", default=0.75),
        listen_session_id_prefix=_optional_string(listen, "session_id_prefix", default="listen") or "listen",
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
    listen = subcommands.add_parser("listen")
    listen.add_argument("--config", type=Path, required=True)
    listen.add_argument("--player")
    listen.add_argument("--max-turns", type=int)
    listen.add_argument("--probe-duration-seconds", type=float)
    listen.add_argument("--voice-threshold", type=float)
    listen.add_argument("--idle-sleep-seconds", type=float)
    listen.add_argument("--cooldown-seconds", type=float)
    listen.add_argument("--session-id-prefix")
    ota_check = subcommands.add_parser("ota-check")
    ota_check.add_argument("--config", type=Path, required=True)
    ota_check.add_argument("--state-dir", type=Path, default=Path("/var/lib/cube-robot"))
    ota_check.add_argument("--current-version", required=True)
    ota_check.add_argument("--protocol-version", default="1")
    ota_check.add_argument("--apply", action="store_true")
    policy_check = subcommands.add_parser("policy-check")
    policy_check.add_argument("--config", type=Path, required=True)
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
    if args.command == "listen":
        config = load_runtime_config(args.config)
        stop_event = Event()
        probe_duration_seconds = (
            args.probe_duration_seconds
            if args.probe_duration_seconds is not None
            else config.listen_probe_duration_seconds
        )
        voice_threshold = args.voice_threshold if args.voice_threshold is not None else config.listen_voice_threshold
        idle_sleep_seconds = (
            args.idle_sleep_seconds if args.idle_sleep_seconds is not None else config.listen_idle_sleep_seconds
        )
        cooldown_seconds = args.cooldown_seconds if args.cooldown_seconds is not None else config.listen_cooldown_seconds
        session_id_prefix = args.session_id_prefix or config.listen_session_id_prefix
        probe_config = replace(config.capture, duration_seconds=probe_duration_seconds)

        def request_stop(_signum: int, _frame: object) -> None:
            stop_event.set()

        def run_turn(session_id: str) -> VoiceOnceResult:
            return run_voice_once(
                _voice_once_config(config, session_id),
                capture=CommandAudioCapture(config.capture),
                playback=CommandAudioPlayback(player=args.player),
            )

        handled_signals = (signal.SIGTERM, signal.SIGINT)
        previous_handlers = {signum: signal.signal(signum, request_stop) for signum in handled_signals}
        try:
            result = run_listen_loop(
                ListenConfig(
                    device_id=config.device_id,
                    probe=probe_config,
                    threshold=voice_threshold,
                    max_turns=args.max_turns,
                    idle_sleep_seconds=idle_sleep_seconds,
                    cooldown_seconds=cooldown_seconds,
                    session_id_prefix=session_id_prefix,
                ),
                probe_capture=CommandAudioCapture(probe_config),
                run_turn=run_turn,
                stop_event=stop_event,
            )
        except KeyboardInterrupt:
            return 0
        finally:
            for signum, previous_handler in previous_handlers.items():
                signal.signal(signum, previous_handler)
        print(json.dumps({"probes": result.probes, "triggered_turns": result.triggered_turns}, ensure_ascii=False))
        return 0
    if args.command == "ota-check":
        config = load_runtime_config(args.config)
        check = check_for_update(
            config.server_url,
            device_id=config.device_id,
            device_token=config.device_token,
            current_version=args.current_version,
            protocol_version=args.protocol_version,
        )
        status = "update_available" if check.update_available else "up_to_date"
        if args.apply and check.update_available and check.manifest is not None:
            apply_update(
                check.manifest,
                state_dir=args.state_dir,
                device_token=config.device_token,
                token_hosts=check.token_hosts,
            )
            status = "applied"
        print(
            json.dumps(
                {
                    "status": status,
                    "target_version": check.manifest.version if check.manifest else None,
                    "reason": check.reason,
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "policy-check":
        config = load_runtime_config(args.config)
        policy = fetch_device_policy(
            config.server_url,
            device_id=config.device_id,
            device_token=config.device_token,
        )
        print(
            json.dumps(
                {
                    "device_id": policy.device_id,
                    "policy_version": policy.policy_version,
                    "target_version": policy.target_version,
                    "config": policy.config,
                    "policy": policy.policy,
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


def _optional_non_negative_float(data: dict[str, object], key: str, *, default: float) -> float:
    value = data.get(key, default)
    if not isinstance(value, int | float) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{key} must be a non-negative number")
    return float(value)


if __name__ == "__main__":
    raise SystemExit(main())
