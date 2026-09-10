"""Dry-run command for the standalone device runtime."""

import argparse
from dataclasses import dataclass
import json
from typing import Sequence

from cube_robot_runtime.audio.playback import PlaybackRecorder
from cube_robot_runtime.device.identity import DeviceIdentity
from cube_robot_runtime.network.client import open_connection
from cube_robot_runtime.protocol.messages import RobotEnvelope


@dataclass(frozen=True)
class RuntimeConfig:
    server_url: str
    device_id: str
    session_id: str = "dry-run-session"


@dataclass(frozen=True)
class DryRunResult:
    sent_types: tuple[str, ...]
    received_texts: tuple[str, ...]


def run_dry_run(config: RuntimeConfig, utterance: str) -> DryRunResult:
    identity = DeviceIdentity(device_id=config.device_id)
    connection = open_connection(config.server_url)
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
        payload={"text": utterance},
    )
    connection.send(heartbeat)
    connection.send(utterance_message)
    response = connection.receive()
    text = str(response.payload["text"])
    recorder.play(text)
    return DryRunResult(
        sent_types=tuple(envelope.type for envelope in connection.sent),
        received_texts=tuple(recorder.texts),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    dry_run = subcommands.add_parser("dry-run")
    dry_run.add_argument("--server-url", required=True)
    dry_run.add_argument("--device-id", required=True)
    dry_run.add_argument("--session-id", default="dry-run-session")
    dry_run.add_argument("--utterance", required=True)
    args = parser.parse_args(argv)
    result = run_dry_run(
        RuntimeConfig(args.server_url, args.device_id, args.session_id),
        args.utterance,
    )
    print(json.dumps({"sent_types": result.sent_types, "received_texts": result.received_texts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
