from fastapi.testclient import TestClient

from agent_hub.app import create_app
from agent_hub.robot.protocol import RobotMessageType, build_envelope


def test_robot_status_endpoint_uses_runtime_registry() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/robot/devices")

    assert response.status_code == 200
    assert response.json()["devices"] == []


def test_robot_websocket_accepts_heartbeat_and_final_utterance() -> None:
    client = TestClient(create_app())

    with client.websocket_connect("/api/v1/robot/ws/pi-lab-01") as ws:
        ws.send_json(
            build_envelope(
                message_type=RobotMessageType.DEVICE_HEARTBEAT,
                device_id="pi-lab-01",
                session_id="voice-session-1",
                payload={"runtime_version": "0.1.0"},
            ).model_dump(mode="json")
        )
        ws.send_json(
            build_envelope(
                message_type=RobotMessageType.SPEECH_PARTIAL,
                device_id="pi-lab-01",
                session_id="voice-session-1",
                payload={"text": "测试语音", "is_final": True},
            ).model_dump(mode="json")
        )

        message = ws.receive_json()

    assert message["type"] == "assistant.text.done"
    assert "测试语音" in message["payload"]["text"]
