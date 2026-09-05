from __future__ import annotations

from datetime import UTC, datetime
from secrets import token_urlsafe
from uuid import UUID

from agent_hub.robot.types import DeviceRecord


class DeviceRegistry:
    def __init__(self) -> None:
        self._by_id: dict[str, DeviceRecord] = {}
        self._by_token: dict[str, DeviceRecord] = {}

    def register(self, *, device_id: str, tenant_id: UUID, user_id: UUID) -> DeviceRecord:
        existing = self._by_id.get(device_id)
        if existing is not None:
            return existing
        record = DeviceRecord(
            device_id=device_id,
            device_token=token_urlsafe(24),
            user_id=user_id,
            tenant_id=tenant_id,
            created_at=datetime.now(UTC),
        )
        self._by_id[device_id] = record
        self._by_token[record.device_token] = record
        return record

    def authenticate(self, device_token: str) -> DeviceRecord | None:
        return self._by_token.get(device_token)

    def get(self, device_id: str) -> DeviceRecord | None:
        return self._by_id.get(device_id)
