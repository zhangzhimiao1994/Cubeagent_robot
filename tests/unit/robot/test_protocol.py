from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from agent_hub.robot.protocol import (
    ROBOT_PROTOCOL_VERSION,
    AudioChunkPayload,
    RobotEnvelope,
    RobotMessageType,
    build_envelope,
    export_robot_protocol_schema,
)


def test_robot_envelope_requires_v1_contract_fields() -> None:
    envelope = build_envelope(
        message_type=RobotMessageType.DEVICE_HEARTBEAT,
        device_id="pi-lab-01",
        session_id="voice-session-1",
        payload={"battery": 82, "network_rssi": -55},
        timestamp=datetime(2026, 9, 10, 12, 0, tzinfo=UTC),
    )

    assert envelope.protocol_version == ROBOT_PROTOCOL_VERSION
    assert envelope.device_id == "pi-lab-01"
    assert envelope.session_id == "voice-session-1"
    assert envelope.type is RobotMessageType.DEVICE_HEARTBEAT
    assert envelope.payload["battery"] == 82


def test_robot_envelope_rejects_unknown_message_type() -> None:
    with pytest.raises(ValidationError):
        RobotEnvelope.model_validate(
            {
                "protocol_version": "1",
                "message_id": "msg-1",
                "session_id": "voice-session-1",
                "device_id": "pi-lab-01",
                "timestamp": "2026-09-10T12:00:00Z",
                "type": "unknown.kind",
                "payload": {},
            }
        )


def test_audio_chunk_payload_bounds_sequence_and_base64() -> None:
    payload = AudioChunkPayload(codec="pcm16", sample_rate_hz=16000, sequence=1, chunk_b64="AQID")

    assert payload.codec == "pcm16"
    assert payload.sample_rate_hz == 16000

    with pytest.raises(ValidationError):
        AudioChunkPayload(
            codec="pcm16",
            sample_rate_hz=16000,
            sequence=0,
            chunk_b64="not base64!!",
        )


def test_protocol_schema_exports_envelope_and_message_types() -> None:
    schema = export_robot_protocol_schema()
    message_types = schema["message_types"]

    assert schema["protocol_version"] == ROBOT_PROTOCOL_VERSION
    assert isinstance(message_types, list)
    assert "device.heartbeat" in message_types
    assert "tts.audio.chunk" in message_types
