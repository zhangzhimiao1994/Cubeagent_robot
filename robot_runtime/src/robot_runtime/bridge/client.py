from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Protocol

from robot_runtime.bridge.protocol import Envelope
from robot_runtime.config import RuntimeConfig

MessageHandler = Callable[[Envelope], Awaitable[None]]


class BridgeClient(Protocol):
    async def connect(self) -> None: ...

    async def close(self) -> None: ...

    async def send(self, envelope: Envelope) -> None: ...

    def on_message(self, handler: MessageHandler) -> None: ...


class LoggingBridgeClient:
    """Dev stub that records outbound frames until WebSocket is configured."""

    def __init__(self, config: RuntimeConfig) -> None:
        self._config = config
        self._handler: MessageHandler | None = None
        self.sent: list[Envelope] = []

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def send(self, envelope: Envelope) -> None:
        self.sent.append(envelope)

    def on_message(self, handler: MessageHandler) -> None:
        self._handler = handler

    async def inject_for_tests(self, envelope: Envelope) -> None:
        if self._handler is not None:
            await self._handler(envelope)

    def dumps(self, envelope: Envelope) -> str:
        return json.dumps(envelope.model_dump(mode="json"), ensure_ascii=False)
