import json

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
