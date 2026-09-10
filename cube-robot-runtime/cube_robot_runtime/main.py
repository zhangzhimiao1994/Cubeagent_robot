"""Dry-run command for the standalone device runtime."""

import argparse
import json
import signal
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from cube_robot_runtime.audio.playback import PlaybackRecorder
from cube_robot_runtime.device.identity import DeviceIdentity
from cube_robot_runtime.network.client import open_connection
from cube_robot_runtime.protocol.messages import RobotEnvelope


@dataclass(frozen=True)
class RuntimeConfig:
    server_url: str
    device_id: str
    session_id: str = "dry-run-session"
    device_token: str | None = None
    timeout_seconds: float = 10.0


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
    if not isinstance(runtime, dict):
        raise TypeError("config must contain a runtime table")
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
    )


def run_runtime(config: RuntimeConfig, *, once: bool, stop_event: Event) -> int:
    while not stop_event.is_set():
        print(json.dumps({"type": "device.heartbeat", "device_id": config.device_id}))
        if once:
            return 0
        stop_event.wait(timeout=30)
    return 0


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


if __name__ == "__main__":
    raise SystemExit(main())
