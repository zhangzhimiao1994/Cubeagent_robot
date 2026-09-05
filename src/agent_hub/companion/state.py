from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from agent_hub.companion.types import CompanionState


class CompanionStateService:
    """Authoritative companion interaction state (cloud)."""

    def __init__(self) -> None:
        self._states: dict[tuple[UUID, UUID], CompanionState] = {}

    def get(self, tenant_id: UUID, user_id: UUID) -> CompanionState:
        key = (tenant_id, user_id)
        existing = self._states.get(key)
        if existing is not None:
            return existing
        state = CompanionState(updated_at=datetime.now(UTC))
        self._states[key] = state
        return state

    def patch(
        self,
        tenant_id: UUID,
        user_id: UUID,
        **updates: object,
    ) -> CompanionState:
        current = self.get(tenant_id, user_id)
        data = current.model_dump(mode="python")
        data.update(updates)
        data["updated_at"] = datetime.now(UTC)
        state = CompanionState.model_validate(data)
        self._states[(tenant_id, user_id)] = state
        return state
