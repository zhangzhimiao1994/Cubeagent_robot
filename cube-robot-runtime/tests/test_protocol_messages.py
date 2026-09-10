import json

import pytest
from cube_robot_runtime.protocol.messages import RobotEnvelope


def test_pi_envelope_round_trip_stdlib_only() -> None:
    envelope = RobotEnvelope.new(
        message_type="device.heartbeat",
        device_id="pi-lab-01",
        session_id="voice-session-1",
        payload={"runtime_version": "0.1.0"},
    )

    parsed = RobotEnvelope.from_json(envelope.to_json())

    assert parsed.protocol_version == "1"
    assert parsed.type == "device.heartbeat"
    assert parsed.payload["runtime_version"] == "0.1.0"
    assert json.loads(parsed.to_json())["device_id"] == "pi-lab-01"


def test_pi_envelope_rejects_wrong_protocol_version() -> None:
    raw = (
        '{"protocol_version":"2","message_id":"m1","session_id":"s1",'
        '"device_id":"pi-lab-01","timestamp":"2026-09-10T00:00:00Z",'
        '"type":"assistant.text.done","payload":{"text":"hello"}}'
    )

    with pytest.raises(ValueError, match="protocol_version"):
        RobotEnvelope.from_json(raw)


def test_pi_envelope_rejects_unknown_message_type() -> None:
    raw = (
        '{"protocol_version":"1","message_id":"m1","session_id":"s1",'
        '"device_id":"pi-lab-01","timestamp":"2026-09-10T00:00:00Z",'
        '"type":"unknown.event","payload":{}}'
    )

    with pytest.raises(ValueError, match="type"):
        RobotEnvelope.from_json(raw)


def test_pi_envelope_rejects_non_object_payload() -> None:
    raw = (
        '{"protocol_version":"1","message_id":"m1","session_id":"s1",'
        '"device_id":"pi-lab-01","timestamp":"2026-09-10T00:00:00Z",'
        '"type":"assistant.text.done","payload":[]}'
    )

    with pytest.raises(TypeError, match="payload"):
        RobotEnvelope.from_json(raw)
