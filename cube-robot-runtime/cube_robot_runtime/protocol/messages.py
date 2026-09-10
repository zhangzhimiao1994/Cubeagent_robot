"""Robot Protocol v1 envelope serialization."""

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

PROTOCOL_VERSION = "1"

MESSAGE_TYPES = frozenset(
    {
        "device.register",
        "device.heartbeat",
        "device.status",
        "audio.start",
        "audio.chunk",
        "audio.end",
        "speech.partial",
        "interaction.event",
        "playback.started",
        "playback.finished",
        "playback.interrupted",
        "screen.event",
        "button.event",
        "session.accepted",
        "assistant.text.delta",
        "assistant.text.done",
        "tts.audio.chunk",
        "tts.audio.done",
        "avatar.state",
        "screen.show",
        "device.command",
        "playback.stop",
        "conversation.end",
        "error",
    }
)


@dataclass(frozen=True)
class RobotEnvelope:
    protocol_version: str
    message_id: str
    session_id: str
    device_id: str
    timestamp: str
    type: str
    payload: dict[str, Any]

    @classmethod
    def new(
        cls,
        *,
        message_type: str,
        device_id: str,
        session_id: str,
        payload: dict[str, Any],
    ) -> "RobotEnvelope":
        return cls(
            protocol_version=PROTOCOL_VERSION,
            message_id=str(uuid4()),
            session_id=session_id,
            device_id=device_id,
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            type=message_type,
            payload=payload,
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> "RobotEnvelope":
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise TypeError("robot envelope must be an object")
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RobotEnvelope":
        protocol_version = _required_string(data, "protocol_version")
        if protocol_version != PROTOCOL_VERSION:
            raise ValueError("protocol_version must be 1")
        message_type = _required_string(data, "type")
        if message_type not in MESSAGE_TYPES:
            raise ValueError("type must be a known Robot Protocol v1 message type")
        timestamp = _required_string(data, "timestamp")
        try:
            datetime.fromisoformat(timestamp)
        except ValueError as exc:
            raise ValueError("timestamp must be ISO-8601") from exc
        payload = data.get("payload")
        if not isinstance(payload, dict):
            raise TypeError("payload must be an object")
        return cls(
            protocol_version=protocol_version,
            message_id=_required_string(data, "message_id"),
            session_id=_required_string(data, "session_id"),
            device_id=_required_string(data, "device_id"),
            timestamp=timestamp,
            type=message_type,
            payload=payload,
        )


def _required_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{key} must be a non-empty unpadded string")
    return value
