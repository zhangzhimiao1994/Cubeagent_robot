from __future__ import annotations

import re
from enum import StrEnum
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:\+(\d+))?$")


class OtaStatus(StrEnum):
    UPDATE_AVAILABLE = "update_available"
    INCOMPATIBLE = "incompatible"
    UP_TO_DATE = "up_to_date"
    DOWNGRADE_BLOCKED = "downgrade_blocked"


class OtaArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    url: str = Field(min_length=1, max_length=2_048)
    sha256: str = Field(min_length=64, max_length=64)
    size_bytes: int = Field(gt=0)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("artifact url must be an absolute https URL")
        return value

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not _SHA256_PATTERN.fullmatch(value):
            raise ValueError("sha256 must be a lowercase sha256 hex digest")
        return value


class OtaManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    version: str = Field(min_length=1, max_length=128)
    channel: str = Field(min_length=1, max_length=32)
    min_protocol_version: str = Field(min_length=1, max_length=32)
    artifact: OtaArtifact
    signature: str = Field(min_length=1, max_length=8_192)
    rollback_version: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("version", "rollback_version")
    @classmethod
    def validate_version(cls, value: str | None) -> str | None:
        if value is not None and _VERSION_PATTERN.fullmatch(value) is None:
            raise ValueError("OTA versions must use YYYY.MM.DD+BUILD format")
        return value


class OtaDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    status: OtaStatus
    target_version: str | None = None
    reason: str


def validate_manifest_for_device(
    manifest: OtaManifest,
    *,
    protocol_version: str,
    current_version: str,
) -> OtaDecision:
    if protocol_version != manifest.min_protocol_version:
        return OtaDecision(
            status=OtaStatus.INCOMPATIBLE,
            reason="device protocol version is incompatible with the OTA manifest",
        )

    target_key = _version_key(manifest.version)
    current_key = _version_key(current_version)
    if target_key > current_key:
        return OtaDecision(
            status=OtaStatus.UPDATE_AVAILABLE,
            target_version=manifest.version,
            reason="a compatible OTA update is available",
        )
    if target_key == current_key:
        return OtaDecision(status=OtaStatus.UP_TO_DATE, reason="device already has this OTA version")
    return OtaDecision(
        status=OtaStatus.DOWNGRADE_BLOCKED,
        reason="manifest version is older than the device version",
    )


def _version_key(version: str) -> tuple[int, int, int, int]:
    match = _VERSION_PATTERN.fullmatch(version)
    if match is None:
        raise ValueError("current_version must use YYYY.MM.DD+BUILD format")
    year, month, day, build = match.groups()
    return int(year), int(month), int(day), int(build or 0)
