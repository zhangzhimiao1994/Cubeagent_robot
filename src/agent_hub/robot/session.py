from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from agent_hub.robot.protocol import RobotEnvelope, RobotMessageType, build_envelope


class RobotSessionState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"


class RobotDeviceStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    device_id: str
    session_id: str
    state: RobotSessionState
    last_seen_at: datetime
    runtime_version: str | None = None
    latency_ms: int | None = None


class RobotStatusSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    devices: tuple[RobotDeviceStatus, ...]


CompanionResponse = Callable[..., str]


class RobotSessionRegistry:
    """In-memory MVP state for connected robot voice sessions."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        responder: CompanionResponse | None = None,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._responder = responder or _default_response
        self._devices: dict[str, RobotDeviceStatus] = {}

    def record(self, envelope: RobotEnvelope) -> tuple[RobotEnvelope, ...]:
        current = self._devices.get(envelope.device_id)
        state = _state_after(
            envelope, current.state if current is not None else RobotSessionState.IDLE
        )
        runtime_version = _payload_string(envelope.payload, "runtime_version")
        latency_ms = _payload_int(envelope.payload, "latency_ms")
        self._devices[envelope.device_id] = RobotDeviceStatus(
            device_id=envelope.device_id,
            session_id=envelope.session_id,
            state=state,
            last_seen_at=self._clock(),
            runtime_version=runtime_version
            if runtime_version is not None
            else (current.runtime_version if current is not None else None),
            latency_ms=latency_ms
            if latency_ms is not None
            else (current.latency_ms if current is not None else None),
        )

        if envelope.type is not RobotMessageType.SPEECH_PARTIAL or not envelope.payload.get(
            "is_final"
        ):
            return ()

        utterance = _payload_string(envelope.payload, "text")
        if utterance is None:
            return ()
        response_text = self._responder(
            utterance,
            device_id=envelope.device_id,
            session_id=envelope.session_id,
        )
        self._devices[envelope.device_id] = self._devices[envelope.device_id].model_copy(
            update={"state": RobotSessionState.IDLE}
        )
        return (
            build_envelope(
                message_type=RobotMessageType.ASSISTANT_TEXT_DONE,
                device_id=envelope.device_id,
                session_id=envelope.session_id,
                payload={"text": response_text},
            ),
            build_envelope(
                message_type=RobotMessageType.CONVERSATION_END,
                device_id=envelope.device_id,
                session_id=envelope.session_id,
                payload={},
            ),
        )

    def status(self, device_id: str | None = None) -> RobotStatusSnapshot:
        devices = tuple(self._devices.values())
        if device_id is not None:
            devices = tuple(device for device in devices if device.device_id == device_id)
        return RobotStatusSnapshot(
            devices=tuple(sorted(devices, key=lambda device: device.device_id))
        )


def _default_response(utterance: str, *, device_id: str, session_id: str) -> str:
    del device_id, session_id
    return f"我听到了：{utterance}"


def _state_after(envelope: RobotEnvelope, current: RobotSessionState) -> RobotSessionState:
    if envelope.type is RobotMessageType.AUDIO_START:
        return RobotSessionState.LISTENING
    if envelope.type is RobotMessageType.SPEECH_PARTIAL and envelope.payload.get("is_final"):
        return RobotSessionState.THINKING
    if envelope.type is RobotMessageType.CONVERSATION_END:
        return RobotSessionState.IDLE
    return current


def _payload_string(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) else None


def _payload_int(payload: dict[str, object], key: str) -> int | None:
    value = payload.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None
