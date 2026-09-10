"""Connections for deterministic and real device dry runs."""

from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlparse

from websocket import create_connection

from cube_robot_runtime.protocol.messages import RobotEnvelope


class RobotConnection(Protocol):
    def send(self, envelope: RobotEnvelope) -> None: ...

    def receive(self) -> RobotEnvelope: ...

    def close(self) -> None: ...


class WebSocketLike(Protocol):
    def send(self, payload: str | bytes, opcode: int = ...) -> int: ...

    def recv(self) -> str | bytes: ...

    def close(self) -> None: ...


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

    def close(self) -> None:
        return None


@dataclass
class WebSocketConnection:
    socket: WebSocketLike

    def send(self, envelope: RobotEnvelope) -> None:
        self.socket.send(envelope.to_json())

    def receive(self) -> RobotEnvelope:
        raw = self.socket.recv()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        if not isinstance(raw, str):
            raise TypeError("websocket message must be text")
        return RobotEnvelope.from_json(raw)

    def close(self) -> None:
        close = getattr(self.socket, "close", None)
        if close is not None:
            close()


def open_connection(
    server_url: str,
    *,
    device_token: str | None = None,
    timeout_seconds: float = 10.0,
) -> RobotConnection:
    scheme = urlparse(server_url).scheme
    if scheme == "mock":
        return MockConnection()
    if scheme in {"ws", "wss"}:
        headers = []
        if device_token:
            headers.append(f"X-Robot-Device-Token: {device_token}")
        return WebSocketConnection(
            create_connection(server_url, header=headers, timeout=timeout_seconds)
        )
    raise ValueError("dry run requires a mock or WebSocket URL")
