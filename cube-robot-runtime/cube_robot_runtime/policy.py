"""Fetch server-managed device policy for the Raspberry Pi runtime."""

import json
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

FetchJson = Callable[[str, dict[str, str]], dict[str, Any]]


@dataclass(frozen=True)
class DevicePolicyBundle:
    device_id: str
    config: dict[str, Any]
    policy: dict[str, Any]
    target_version: str | None
    policy_version: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DevicePolicyBundle":
        config = data.get("config")
        policy = data.get("policy")
        target_version = data.get("target_version")
        if not isinstance(config, dict):
            raise TypeError("device policy config must be an object")
        if not isinstance(policy, dict):
            raise TypeError("device policy policy must be an object")
        if target_version is not None and not isinstance(target_version, str):
            raise TypeError("device policy target_version must be a string or null")
        return cls(
            device_id=_required_string(data, "device_id"),
            config=dict(config),
            policy=dict(policy),
            target_version=target_version,
            policy_version=_required_string(data, "policy_version"),
        )


def fetch_device_policy(
    server_url: str,
    *,
    device_id: str,
    device_token: str | None,
    fetch_json: FetchJson | None = None,
) -> DevicePolicyBundle:
    url = _policy_url(server_url, device_id=device_id)
    headers = {"X-Robot-Device-Token": device_token} if device_token else {}
    return DevicePolicyBundle.from_dict((fetch_json or _fetch_json)(url, headers))


def _policy_url(server_url: str, *, device_id: str) -> str:
    parsed = urlsplit(server_url.rstrip("/"))
    if parsed.scheme not in {"http", "https", "ws", "wss"} or not parsed.netloc:
        raise ValueError("runtime.server_url must be an absolute HTTP(S) or WS(S) URL")
    scheme = {"ws": "http", "wss": "https"}.get(parsed.scheme, parsed.scheme)
    marker = "/api/v1/robot"
    base_path = parsed.path.split(marker, 1)[0].rstrip("/")
    path = f"{base_path}/api/v1/robot/policy/{quote(device_id, safe='')}"
    return urlunsplit((scheme, parsed.netloc, path, "", ""))


def _fetch_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("device policy response must be an object")
    return payload


def _required_string(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"device policy {key} must be a non-empty string")
    return value
