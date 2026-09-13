from __future__ import annotations

import re
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ROBOT_DEVICE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"
_ROBOT_CHANNEL_PATTERN = r"^[a-z][a-z0-9_-]{0,31}$"
_MAINTENANCE_WINDOW_PATTERN = re.compile(r"^(?P<start>\d{2}:\d{2})-(?P<end>\d{2}:\d{2})$")


class RobotDeviceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(default="", max_length=128)
    locale: str = Field(default="zh-CN", min_length=2, max_length=32)
    voice_preset_id: str | None = Field(default=None, max_length=128)
    volume: int = Field(default=70, ge=0, le=100)
    wake_word_required: bool = True

    @field_validator("display_name", "locale")
    @classmethod
    def trim_strings(cls, value: str) -> str:
        return value.strip()

    @field_validator("voice_preset_id")
    @classmethod
    def normalize_optional_voice_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class RobotDevicePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ota_channel: str = Field(default="stable", pattern=_ROBOT_CHANNEL_PATTERN)
    auto_update: bool = True
    maintenance_window: str = Field(default="03:00-05:00", max_length=32)
    telemetry_enabled: bool = True

    @field_validator("maintenance_window")
    @classmethod
    def validate_maintenance_window(cls, value: str) -> str:
        match = _MAINTENANCE_WINDOW_PATTERN.fullmatch(value.strip())
        if match is None:
            raise ValueError("maintenance window must use HH:MM-HH:MM")
        for field_name in ("start", "end"):
            hour, minute = (int(part) for part in match.group(field_name).split(":"))
            if hour > 23 or minute > 59:
                raise ValueError("maintenance window must use valid 24-hour times")
        return value.strip()


class RobotDeviceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(pattern=_ROBOT_DEVICE_ID_PATTERN)
    config: RobotDeviceConfig = Field(default_factory=RobotDeviceConfig)
    policy: RobotDevicePolicy = Field(default_factory=RobotDevicePolicy)
    target_version: str | None = Field(default=None, max_length=128)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RobotFleetSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    devices: list[RobotDeviceRecord] = Field(default_factory=list, max_length=128)


class RobotManagedDevice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str
    name: str = ""
    status: str = Field(default="offline", pattern=r"^(online|offline)$")
    current_version: str | None = None
    target_version: str | None = None
    last_seen_at: datetime | None = None
    config: RobotDeviceConfig = Field(default_factory=RobotDeviceConfig)
    policy: RobotDevicePolicy = Field(default_factory=RobotDevicePolicy)


class RobotOtaTargetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str | None = Field(default=None, max_length=128)

    @field_validator("version")
    @classmethod
    def normalize_target_version(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class RobotDevicePolicyBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str
    config: RobotDeviceConfig
    policy: RobotDevicePolicy
    target_version: str | None
    policy_version: str
