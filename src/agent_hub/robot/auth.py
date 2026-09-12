from __future__ import annotations

import secrets
from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import SecretStr


@dataclass(frozen=True)
class RobotDeviceTokenStore:
    """Authenticate robot devices separately from human Web sessions."""

    _tokens_by_device: Mapping[str, str]

    @classmethod
    def from_secret(cls, raw: SecretStr | str | None) -> RobotDeviceTokenStore:
        if raw is None:
            return cls({})
        value = raw.get_secret_value() if isinstance(raw, SecretStr) else raw
        tokens: dict[str, str] = {}
        for entry in value.replace("\n", ",").split(","):
            normalized = entry.strip()
            if not normalized:
                continue
            if ":" not in normalized:
                raise ValueError("robot device tokens must use device_id:token entries")
            device_id, token = normalized.split(":", 1)
            device_id = device_id.strip()
            token = token.strip()
            if not device_id or not token:
                raise ValueError("robot device token entries require device_id and token")
            tokens[device_id] = token
        return cls(tokens)

    def authenticate(self, device_id: str, token: str | None) -> bool:
        expected = self._tokens_by_device.get(device_id)
        if expected is None or token is None:
            return False
        try:
            expected_bytes = expected.encode("ascii")
            token_bytes = token.encode("ascii")
        except UnicodeEncodeError:
            return False
        return secrets.compare_digest(expected_bytes, token_bytes)
