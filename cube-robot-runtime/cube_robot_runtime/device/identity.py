"""Device identity value object."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceIdentity:
    device_id: str
