from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from agent_hub.robot.types import RobotSession


class RobotSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, RobotSession] = {}

    def create(self, *, device_id: str, tenant_id: UUID, user_id: UUID) -> RobotSession:
        session = RobotSession(
            session_id=str(uuid4()),
            device_id=device_id,
            user_id=user_id,
            tenant_id=tenant_id,
            created_at=datetime.now(UTC),
        )
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> RobotSession | None:
        return self._sessions.get(session_id)

    def end(self, session_id: str) -> RobotSession | None:
        session = self._sessions.get(session_id)
        if session is None or session.ended_at is not None:
            return session
        ended = session.model_copy(update={"ended_at": datetime.now(UTC)})
        self._sessions[session_id] = ended
        return ended
