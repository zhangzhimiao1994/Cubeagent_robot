from __future__ import annotations

from uuid import uuid4

from agent_hub.companion.state import CompanionStateService
from agent_hub.robot.types import BridgeEnvelope, RobotSession


class RobotBridgeHub:
    """Cloud-side handler for device bridge messages."""

    def __init__(self, companion_states: CompanionStateService | None = None) -> None:
        self._companion_states = companion_states or CompanionStateService()
        self._cancelled_turns: set[str] = set()

    def handle_device_message(
        self, session: RobotSession, envelope: BridgeEnvelope
    ) -> list[BridgeEnvelope]:
        if envelope.type == "ping":
            return [BridgeEnvelope(type="pong", payload={})]
        if envelope.type == "hello":
            state = self._companion_states.get(session.tenant_id, session.user_id)
            return [
                BridgeEnvelope(
                    type="hello.ok",
                    payload={
                        "session_id": session.session_id,
                        "companion_state": state.model_dump(mode="json"),
                    },
                )
            ]
        if envelope.type == "barge_in" and envelope.turn_id:
            self._cancelled_turns.add(envelope.turn_id)
            return [BridgeEnvelope(type="cancel", turn_id=envelope.turn_id)]
        if envelope.type == "utterance.end":
            if envelope.turn_id and envelope.turn_id in self._cancelled_turns:
                return []
            reply_id = str(uuid4())
            return [
                BridgeEnvelope(
                    type="assistant.text",
                    turn_id=envelope.turn_id,
                    reply_id=reply_id,
                    payload={"text": "我在，你说。"},
                ),
                BridgeEnvelope(
                    type="assistant.end",
                    turn_id=envelope.turn_id,
                    reply_id=reply_id,
                ),
            ]
        if envelope.type == "state.patch":
            state = self._companion_states.patch(
                session.tenant_id, session.user_id, **envelope.payload
            )
            return [
                BridgeEnvelope(
                    type="state.sync",
                    payload=state.model_dump(mode="json"),
                )
            ]
        return []
