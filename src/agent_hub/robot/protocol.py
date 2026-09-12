from __future__ import annotations

import base64
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

ROBOT_PROTOCOL_VERSION = "1"


class RobotMessageType(StrEnum):
    DEVICE_REGISTER = "device.register"
    DEVICE_HEARTBEAT = "device.heartbeat"
    DEVICE_STATUS = "device.status"
    AUDIO_START = "audio.start"
    AUDIO_CHUNK = "audio.chunk"
    AUDIO_END = "audio.end"
    SPEECH_PARTIAL = "speech.partial"
    INTERACTION_EVENT = "interaction.event"
    PLAYBACK_STARTED = "playback.started"
    PLAYBACK_FINISHED = "playback.finished"
    PLAYBACK_INTERRUPTED = "playback.interrupted"
    SCREEN_EVENT = "screen.event"
    BUTTON_EVENT = "button.event"
    SESSION_ACCEPTED = "session.accepted"
    ASSISTANT_TEXT_DELTA = "assistant.text.delta"
    ASSISTANT_TEXT_DONE = "assistant.text.done"
    TTS_AUDIO_CHUNK = "tts.audio.chunk"
    TTS_AUDIO_DONE = "tts.audio.done"
    AVATAR_STATE = "avatar.state"
    SCREEN_SHOW = "screen.show"
    DEVICE_COMMAND = "device.command"
    PLAYBACK_STOP = "playback.stop"
    CONVERSATION_END = "conversation.end"
    ERROR = "error"


class AudioChunkPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    codec: Literal["pcm16", "opus", "wav", "mp3", "aac", "flac", "ogg", "m4a"]
    sample_rate_hz: int = Field(ge=8_000, le=48_000)
    sequence: int = Field(ge=1)
    chunk_b64: str = Field(min_length=1)

    @field_validator("chunk_b64")
    @classmethod
    def validate_base64(cls, value: str) -> str:
        try:
            base64.b64decode(value, validate=True)
        except ValueError as exc:
            raise ValueError("chunk_b64 must be valid base64") from exc
        return value


class RobotEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    protocol_version: Literal["1"]
    message_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    timestamp: datetime
    type: RobotMessageType
    payload: dict[str, object]

    @field_validator("message_id", "session_id", "device_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        if value != value.strip() or any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("identifiers must be unpadded printable text")
        return value

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(UTC)


def build_envelope(
    *,
    message_type: RobotMessageType | str,
    device_id: str,
    session_id: str,
    payload: Mapping[str, object],
    timestamp: datetime | None = None,
) -> RobotEnvelope:
    return RobotEnvelope(
        protocol_version="1",
        message_id=uuid4().hex,
        session_id=session_id,
        device_id=device_id,
        timestamp=timestamp or datetime.now(UTC),
        type=RobotMessageType(message_type),
        payload=dict(payload),
    )


def export_robot_protocol_schema() -> dict[str, object]:
    return {
        "protocol_version": ROBOT_PROTOCOL_VERSION,
        "envelope": RobotEnvelope.model_json_schema(),
        "audio_chunk_payload": AudioChunkPayload.model_json_schema(),
        "message_types": [message_type.value for message_type in RobotMessageType],
    }
