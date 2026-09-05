from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CompanionState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    persona_id: str = Field(default="default", min_length=1, max_length=64)
    relationship_level: int = Field(default=0, ge=0, le=100)
    mood: str = Field(default="neutral", min_length=1, max_length=64)
    scene: str = Field(default="idle_chat", min_length=1, max_length=64)
    last_user_topics: list[str] = Field(default_factory=list, max_length=32)
    updated_at: datetime


class LifeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: UUID
    user_id: UUID
    title: str = Field(min_length=1, max_length=256)
    summary: str = Field(min_length=1, max_length=4096)
    occurred_at: datetime
    tags: list[str] = Field(default_factory=list, max_length=16)
    created_at: datetime
