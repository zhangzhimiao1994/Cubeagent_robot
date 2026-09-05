from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from agent_hub.companion.types import LifeEvent


class LifeTimelineService:
    """Long-term life events for companionship memory."""

    def __init__(self) -> None:
        self._events: dict[UUID, list[LifeEvent]] = {}

    def add(
        self,
        *,
        user_id: UUID,
        title: str,
        summary: str,
        occurred_at: datetime | None = None,
        tags: list[str] | None = None,
    ) -> LifeEvent:
        event = LifeEvent(
            id=uuid4(),
            user_id=user_id,
            title=title,
            summary=summary,
            occurred_at=occurred_at or datetime.now(UTC),
            tags=tags or [],
            created_at=datetime.now(UTC),
        )
        self._events.setdefault(user_id, []).append(event)
        return event

    def list_for_user(self, user_id: UUID, *, limit: int = 50) -> tuple[LifeEvent, ...]:
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        events = sorted(
            self._events.get(user_id, []),
            key=lambda item: item.occurred_at,
            reverse=True,
        )
        return tuple(events[:limit])
