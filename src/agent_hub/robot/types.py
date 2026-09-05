from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DeviceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    device_id: str = Field(min_length=1, max_length=128)
    device_token: str = Field(min_length=1, max_length=256)
    user_id: UUID
    tenant_id: UUID
    created_at: datetime


class RobotSession(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    session_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    user_id: UUID
    tenant_id: UUID
    created_at: datetime
    ended_at: datetime | None = None


class BridgeEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    type: str = Field(min_length=1, max_length=64)
    turn_id: str | None = None
    reply_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
