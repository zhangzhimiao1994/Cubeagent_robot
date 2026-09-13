"""Validate OTA metadata, fetch runtime artifacts, and switch device releases."""

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode, urlsplit, urlunsplit


@dataclass(frozen=True)
class UpdateArtifact:
    url: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class UpdateManifest:
    version: str
    channel: str
    min_protocol_version: str
    artifact: UpdateArtifact
    signature: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "UpdateManifest":
        artifact_data = data.get("artifact")
        if not isinstance(artifact_data, Mapping):
            raise TypeError("manifest artifact must be an object")
        return cls(
            version=_required_string(data, "version"),
            channel=_required_string(data, "channel"),
            min_protocol_version=_required_string(data, "min_protocol_version"),
            artifact=UpdateArtifact(
                url=_required_string(artifact_data, "url"),
                sha256=_required_sha256(artifact_data, "sha256"),
                size_bytes=_required_nonnegative_int(artifact_data, "size_bytes"),
            ),
            signature=_required_string(data, "signature"),
        )

    def compatible_with(self, *, protocol_version: str) -> bool:
        return _version_parts(protocol_version) >= _version_parts(self.min_protocol_version)


@dataclass(frozen=True)
class ReleaseSwitch:
    current: Path
    next_release: Path
    rollback_release: Path | None


FetchArtifact = Callable[[str, dict[str, str]], bytes]
FetchJson = Callable[[str, dict[str, str]], dict[str, Any]]


@dataclass(frozen=True)
class UpdateCheck:
    update_available: bool
    manifest: UpdateManifest | None
    token_hosts: set[str]
    reason: str


def verify_artifact(path: Path, expected_sha256: str) -> bool:
    if len(expected_sha256) != 64:
        return False
    try:
        int(expected_sha256, 16)
    except ValueError:
        return False
    digest = hashlib.sha256()
    try:
        with path.open("rb") as artifact:
            for block in iter(lambda: artifact.read(1024 * 1024), b""):
                digest.update(block)
    except OSError:
        return False
    return digest.hexdigest() == expected_sha256.lower()


def select_release(*, current: Path, candidate: Path, previous: Path | None) -> ReleaseSwitch:
    return ReleaseSwitch(current=current, next_release=candidate, rollback_release=previous)


def check_for_update(
    server_url: str,
    *,
    device_id: str,
    device_token: str | None,
    current_version: str,
    protocol_version: str,
    fetch_json: FetchJson | None = None,
) -> UpdateCheck:
    manifest_url = _manifest_url(
        server_url,
        device_id=device_id,
        current_version=current_version,
        protocol_version=protocol_version,
    )
    headers = {"X-Robot-Device-Token": device_token} if device_token else {}
    payload = (fetch_json or _fetch_json)(manifest_url, headers)
    decision = payload.get("decision")
    if not isinstance(decision, Mapping):
        raise TypeError("OTA manifest response decision must be an object")
    reason = decision.get("reason")
    status = decision.get("status")
    manifest_data = payload.get("manifest")
    manifest = UpdateManifest.from_dict(manifest_data) if isinstance(manifest_data, Mapping) else None
    control_host = urlsplit(server_url).hostname
    token_hosts = {control_host} if control_host else set()
    return UpdateCheck(
        update_available=status == "update_available" and manifest is not None,
        manifest=manifest,
        token_hosts=token_hosts,
        reason=reason if isinstance(reason, str) else "",
    )


def apply_update(
    manifest: UpdateManifest,
    *,
    state_dir: Path,
    device_token: str | None,
    token_hosts: set[str] | None = None,
    fetch: FetchArtifact | None = None,
) -> ReleaseSwitch:
    """Download a verified runtime artifact and atomically switch current release."""

    releases_dir = state_dir / "releases"
    downloads_dir = state_dir / "downloads"
    releases_dir.mkdir(parents=True, exist_ok=True)
    downloads_dir.mkdir(parents=True, exist_ok=True)
    if urlsplit(manifest.artifact.url).scheme != "https":
        raise ValueError("OTA artifact URL must use HTTPS")

    headers = _artifact_headers(
        manifest.artifact.url,
        device_token=device_token,
        token_hosts=token_hosts or set(),
    )
    artifact_bytes = (fetch or _fetch_artifact)(manifest.artifact.url, headers)
    if len(artifact_bytes) != manifest.artifact.size_bytes:
        raise ValueError("downloaded artifact size does not match manifest")

    artifact_path = downloads_dir / f"{manifest.version}.tar.gz"
    artifact_path.write_bytes(artifact_bytes)
    if not verify_artifact(artifact_path, manifest.artifact.sha256):
        raise ValueError("downloaded artifact sha256 does not match manifest")

    candidate = releases_dir / manifest.version
    with tempfile.TemporaryDirectory(prefix=f".{manifest.version}.", dir=releases_dir) as staging_name:
        staging = Path(staging_name)
        _extract_tarball_safely(artifact_path, staging)
        if candidate.exists():
            shutil.rmtree(candidate)
        staging.replace(candidate)

    current = state_dir / "current"
    previous = current.resolve() if current.exists() else None
    _switch_current(current=current, candidate=candidate)
    return select_release(current=current, candidate=candidate, previous=previous)


def _artifact_headers(
    artifact_url: str,
    *,
    device_token: str | None,
    token_hosts: set[str],
) -> dict[str, str]:
    if not device_token:
        return {}
    hostname = urlsplit(artifact_url).hostname
    if hostname is None or hostname not in token_hosts:
        return {}
    return {"X-Robot-Device-Token": device_token}


def _fetch_artifact(url: str, headers: dict[str, str]) -> bytes:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def _fetch_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("OTA manifest response must be an object")
    return payload


def _manifest_url(
    server_url: str,
    *,
    device_id: str,
    current_version: str,
    protocol_version: str,
) -> str:
    parsed = urlsplit(server_url.rstrip("/"))
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("runtime.server_url must be an absolute HTTPS URL for OTA")
    path = f"{parsed.path.rstrip('/')}/api/v1/robot/ota/manifest/{quote(device_id, safe='')}"
    query = urlencode(
        {
            "current_version": current_version,
            "protocol_version": protocol_version,
        }
    )
    return urlunsplit((parsed.scheme, parsed.netloc, path, query, ""))


def _switch_current(*, current: Path, candidate: Path) -> None:
    tmp_link = current.parent / ".current.tmp"
    if tmp_link.exists() or tmp_link.is_symlink():
        if tmp_link.is_dir() and not tmp_link.is_symlink():
            shutil.rmtree(tmp_link)
        else:
            tmp_link.unlink()
    try:
        os.symlink(candidate, tmp_link, target_is_directory=True)
        os.replace(tmp_link, current)
        return
    except OSError:
        if tmp_link.exists() or tmp_link.is_symlink():
            if tmp_link.is_dir() and not tmp_link.is_symlink():
                shutil.rmtree(tmp_link)
            else:
                tmp_link.unlink()

    shutil.copytree(candidate, tmp_link)
    if current.exists() or current.is_symlink():
        if current.is_dir() and not current.is_symlink():
            shutil.rmtree(current)
        else:
            current.unlink()
    os.replace(tmp_link, current)


def _extract_tarball_safely(artifact_path: Path, target_dir: Path) -> None:
    target_root = target_dir.resolve()
    with tarfile.open(artifact_path, mode="r:gz") as archive:
        for member in archive.getmembers():
            member_path = (target_root / member.name).resolve()
            if not member_path.is_relative_to(target_root):
                raise ValueError("artifact contains a path outside the release directory")
            if member.issym() or member.islnk():
                raise ValueError("artifact must not contain links")
        archive.extractall(target_root, filter="data")


def _required_string(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"manifest {key} must be a non-empty string")
    return value


def _required_sha256(data: Mapping[str, Any], key: str) -> str:
    value = _required_string(data, key)
    if len(value) != 64:
        raise ValueError("manifest artifact sha256 must be 64 hexadecimal characters")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError("manifest artifact sha256 must be hexadecimal") from exc
    return value.lower()


def _required_nonnegative_int(data: Mapping[str, Any], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"manifest {key} must be a non-negative integer")
    return value


def _version_parts(version: str) -> tuple[int, ...]:
    try:
        parts = tuple(int(part) for part in version.split("."))
    except ValueError as exc:
        raise ValueError("protocol version must contain numeric components") from exc
    if not parts or any(part < 0 for part in parts):
        raise ValueError("protocol version must contain numeric components")
    return parts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan a device runtime OTA update")
    parser.add_argument("--config", type=Path, default=Path("/etc/cube-robot/robot.toml"))
    parser.add_argument("--state-dir", type=Path, default=Path("/var/lib/cube-robot"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.dry_run:
        print(f"dry-run: would inspect {args.config}")
        print(f"dry-run: would stage releases under {args.state_dir / 'releases'}")
        print(f"dry-run: would update {args.state_dir / 'current'} after verification")
        return 0
    parser.error("only --dry-run is supported until a transport is configured")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
