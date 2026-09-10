from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_hub.db.models import AdminResourceRow


class CognitionRepository(Protocol):
    async def upsert(
        self, record_type: str, record_id: str, payload: dict[str, object]
    ) -> dict[str, object]: ...

    async def get(self, record_type: str, record_id: str) -> dict[str, object] | None: ...

    async def list(self, record_type: str | None = None) -> tuple[dict[str, object], ...]: ...

    async def delete(self, record_type: str, record_id: str) -> bool: ...


class InMemoryCognitionRepository:
    def __init__(self, *, tenant_id: UUID, user_id: UUID) -> None:
        self._tenant_id = tenant_id
        self._user_id = user_id
        self._records: dict[tuple[UUID, UUID, str, str], dict[str, object]] = {}
        self._lock = asyncio.Lock()

    async def upsert(
        self, record_type: str, record_id: str, payload: dict[str, object]
    ) -> dict[str, object]:
        normalized = _payload(record_type, record_id, payload)
        async with self._lock:
            self._records[(self._tenant_id, self._user_id, record_type, record_id)] = normalized
        return dict(normalized)

    async def get(self, record_type: str, record_id: str) -> dict[str, object] | None:
        async with self._lock:
            found = self._records.get((self._tenant_id, self._user_id, record_type, record_id))
            return dict(found) if found is not None else None

    async def list(self, record_type: str | None = None) -> tuple[dict[str, object], ...]:
        async with self._lock:
            rows = [
                dict(payload)
                for (tenant_id, user_id, found_type, _), payload in self._records.items()
                if tenant_id == self._tenant_id
                and user_id == self._user_id
                and (record_type is None or found_type == record_type)
            ]
        return tuple(rows)

    async def delete(self, record_type: str, record_id: str) -> bool:
        async with self._lock:
            return self._records.pop((self._tenant_id, self._user_id, record_type, record_id), None) is not None


class AdminResourceCognitionRepository:
    def __init__(
        self,
        *,
        session_factory: Callable[[], AsyncSession],
        tenant_id: UUID,
        user_id: UUID,
    ) -> None:
        self._session_factory = session_factory
        self._tenant_id = tenant_id
        self._user_id = user_id

    async def upsert(
        self, record_type: str, record_id: str, payload: dict[str, object]
    ) -> dict[str, object]:
        normalized = _payload(record_type, record_id, payload)
        normalized["tenant_id"] = str(self._tenant_id)
        normalized["user_id"] = str(self._user_id)
        resource_id = _resource_id(record_type, record_id)
        async with self._session_factory() as session:
            row = await session.scalar(
                select(AdminResourceRow)
                .where(AdminResourceRow.tenant_id == self._tenant_id)
                .where(AdminResourceRow.kind == "cognition")
                .where(AdminResourceRow.resource_id == resource_id)
            )
            if row is None:
                session.add(
                    AdminResourceRow(
                        tenant_id=self._tenant_id,
                        kind="cognition",
                        resource_id=resource_id,
                        payload=normalized,
                    )
                )
            else:
                row.payload = normalized
            await session.commit()
        return dict(normalized)

    async def get(self, record_type: str, record_id: str) -> dict[str, object] | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(AdminResourceRow)
                .where(AdminResourceRow.tenant_id == self._tenant_id)
                .where(AdminResourceRow.kind == "cognition")
                .where(AdminResourceRow.resource_id == _resource_id(record_type, record_id))
            )
        if row is None or row.payload.get("user_id") != str(self._user_id):
            return None
        return dict(row.payload)

    async def list(self, record_type: str | None = None) -> tuple[dict[str, object], ...]:
        async with self._session_factory() as session:
            rows = list(
                await session.scalars(
                    select(AdminResourceRow)
                    .where(AdminResourceRow.tenant_id == self._tenant_id)
                    .where(AdminResourceRow.kind == "cognition")
                    .order_by(AdminResourceRow.created_at, AdminResourceRow.resource_id)
                )
            )
        return tuple(
            dict(row.payload)
            for row in rows
            if row.payload.get("user_id") == str(self._user_id)
            and (record_type is None or row.payload.get("record_type") == record_type)
        )

    async def delete(self, record_type: str, record_id: str) -> bool:
        resource_id = _resource_id(record_type, record_id)
        async with self._session_factory() as session:
            row = await session.scalar(
                select(AdminResourceRow)
                .where(AdminResourceRow.tenant_id == self._tenant_id)
                .where(AdminResourceRow.kind == "cognition")
                .where(AdminResourceRow.resource_id == resource_id)
            )
            if row is None or row.payload.get("user_id") != str(self._user_id):
                return False
            await session.execute(delete(AdminResourceRow).where(AdminResourceRow.id == row.id))
            await session.commit()
        return True


def _payload(record_type: str, record_id: str, payload: Mapping[str, object]) -> dict[str, object]:
    normalized = dict(payload)
    normalized["record_type"] = record_type
    normalized["id"] = record_id
    return normalized


def _resource_id(record_type: str, record_id: str) -> str:
    return f"{record_type}:{record_id}"
