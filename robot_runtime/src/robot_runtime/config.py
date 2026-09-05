from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeConfig(BaseSettings):
    """Device-side runtime configuration (env prefix ROBOT_)."""

    model_config = SettingsConfigDict(env_prefix="ROBOT_", extra="ignore")

    device_id: str = Field(default="pi-prototype-01", min_length=1)
    cloud_ws_url: str = Field(default="wss://127.0.0.1/api/robot/v1/ws")
    device_token: str = Field(default="")
    sample_rate_hz: int = Field(default=16000, ge=8000, le=48000)
    channels: int = Field(default=1, ge=1, le=2)
    enable_barge_in: bool = True
    prefer_edge_model: bool = False
