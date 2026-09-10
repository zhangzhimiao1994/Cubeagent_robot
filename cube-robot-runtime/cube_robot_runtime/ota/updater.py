"""Validate OTA metadata and plan release switches without mutating disk state."""

import argparse
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence


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
            raise ValueError("manifest artifact must be an object")
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
