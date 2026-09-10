"""Robot Protocol v1 envelope serialization."""

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


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
            protocol_version="1",
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
        return cls(**json.loads(raw))
