"""Mock connection for deterministic device dry runs."""

from dataclasses import dataclass, field
from urllib.parse import urlparse

from cube_robot_runtime.protocol.messages import RobotEnvelope


@dataclass
class MockConnection:
    sent: list[RobotEnvelope] = field(default_factory=list)

    def send(self, envelope: RobotEnvelope) -> None:
        self.sent.append(envelope)

    def receive(self) -> RobotEnvelope:
        utterance = str(self.sent[-1].payload["text"])
        return RobotEnvelope.new(
            message_type="assistant.text.done",
            device_id=self.sent[-1].device_id,
            session_id=self.sent[-1].session_id,
            payload={"text": f"我听到了：{utterance}"},
        )


def open_connection(server_url: str) -> MockConnection:
    if urlparse(server_url).scheme not in {"mock", "ws", "wss"}:
        raise ValueError("dry run requires a mock or WebSocket URL")
    return MockConnection()
