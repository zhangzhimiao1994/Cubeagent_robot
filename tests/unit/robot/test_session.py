from datetime import UTC, datetime

from agent_hub.robot.protocol import RobotMessageType, build_envelope
from agent_hub.robot.session import RobotSessionRegistry, RobotSessionState


def test_registry_accepts_heartbeat_and_reports_online_status() -> None:
    registry = RobotSessionRegistry(clock=lambda: datetime(2026, 9, 10, 12, 0, tzinfo=UTC))

    response = registry.record(
        build_envelope(
            message_type=RobotMessageType.DEVICE_HEARTBEAT,
            device_id="pi-lab-01",
            session_id="voice-session-1",
            payload={"runtime_version": "0.1.0", "latency_ms": 18},
        )
    )

    snapshot = registry.status("pi-lab-01")

    assert response == ()
    assert snapshot.devices[0].device_id == "pi-lab-01"
    assert snapshot.devices[0].state is RobotSessionState.IDLE
    assert snapshot.devices[0].runtime_version == "0.1.0"


def test_registry_turns_final_speech_partial_into_assistant_text_done() -> None:
    registry = RobotSessionRegistry()

    response = registry.record(
        build_envelope(
            message_type=RobotMessageType.SPEECH_PARTIAL,
            device_id="pi-lab-01",
            session_id="voice-session-1",
            payload={"text": "你好", "is_final": True},
        )
    )

    assert [item.type for item in response] == [
        RobotMessageType.ASSISTANT_TEXT_DONE,
        RobotMessageType.CONVERSATION_END,
    ]
    assert "你好" in str(response[0].payload["text"])
