import hashlib
import io
import tarfile
from pathlib import Path

import pytest
from cube_robot_runtime.main import main
from cube_robot_runtime.ota.updater import (
    UpdateCheck,
    UpdateManifest,
    apply_update,
    check_for_update,
    select_release,
    verify_artifact,
)


def test_verify_artifact_matches_sha256(tmp_path: Path) -> None:
    artifact = tmp_path / "runtime.tgz"
    artifact.write_bytes(b"runtime")

    assert verify_artifact(artifact, "d92c6a81b2ff50096bcda80885427d1f59a25b5f483f7055523504925d16ab23") is True
    assert verify_artifact(artifact, "a" * 64) is False


def test_manifest_rejects_protocol_too_new() -> None:
    manifest = UpdateManifest.from_dict(
        {
            "version": "2026.09.10+001",
            "channel": "stable",
            "min_protocol_version": "2",
            "artifact": {
                "url": "https://updates.example.com/runtime.tgz",
                "sha256": "a" * 64,
                "size_bytes": 10,
            },
            "signature": "sig-test",
        }
    )

    assert manifest.compatible_with(protocol_version="1") is False


def test_manifest_rejects_non_object_artifact_with_type_error() -> None:
    with pytest.raises(TypeError, match="manifest artifact must be an object"):
        UpdateManifest.from_dict(
            {
                "version": "2026.09.10+001",
                "channel": "stable",
                "min_protocol_version": "1",
                "artifact": [],
                "signature": "sig-test",
            }
        )


def test_select_release_preserves_previous_for_rollback(tmp_path: Path) -> None:
    current = tmp_path / "current"
    candidate = tmp_path / "releases" / "2026.09.10"
    previous = tmp_path / "releases" / "2026.09.01"
    candidate.mkdir(parents=True)
    previous.mkdir(parents=True)

    switch = select_release(current=current, candidate=candidate, previous=previous)

    assert switch.current == current
    assert switch.next_release == candidate
    assert switch.rollback_release == previous


def test_apply_update_downloads_verifies_extracts_and_switches_current(tmp_path: Path) -> None:
    artifact = io.BytesIO()
    with tarfile.open(fileobj=artifact, mode="w:gz") as archive:
        payload = b"#!/usr/bin/env python3\n"
        info = tarfile.TarInfo("bin/python")
        info.mode = 0o755
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    artifact_bytes = artifact.getvalue()
    manifest = UpdateManifest.from_dict(
        {
            "version": "2026.09.13+1",
            "channel": "stable",
            "min_protocol_version": "1",
            "artifact": {
                "url": "https://updates.example.test/runtime.tar.gz",
                "sha256": hashlib.sha256(artifact_bytes).hexdigest(),
                "size_bytes": len(artifact_bytes),
            },
            "signature": "sha256",
        }
    )
    requested_headers: dict[str, str] = {}

    def fetch(url: str, headers: dict[str, str]) -> bytes:
        requested_headers.update(headers)
        assert url == manifest.artifact.url
        return artifact_bytes

    result = apply_update(
        manifest,
        state_dir=tmp_path,
        device_token="device-token",
        token_hosts={"updates.example.test"},
        fetch=fetch,
    )

    assert result.next_release == tmp_path / "releases" / "2026.09.13+1"
    assert (tmp_path / "current" / "bin" / "python").read_bytes() == b"#!/usr/bin/env python3\n"
    assert (result.next_release / "bin" / "python").read_bytes() == b"#!/usr/bin/env python3\n"
    assert requested_headers == {"X-Robot-Device-Token": "device-token"}


def test_check_for_update_fetches_device_manifest_with_token() -> None:
    requested_headers: dict[str, str] = {}

    def fetch_json(url: str, headers: dict[str, str]) -> dict[str, object]:
        requested_headers.update(headers)
        assert url == (
            "https://control.example.test/api/v1/robot/ota/manifest/pi-lab-01"
            "?current_version=2026.09.13%2B0&protocol_version=1"
        )
        return {
            "manifest": {
                "version": "2026.09.13+1",
                "channel": "stable",
                "min_protocol_version": "1",
                "artifact": {
                    "url": "https://control.example.test/api/v1/robot/ota/artifacts/pi-lab-01/2026.09.13+1/runtime.tgz",
                    "sha256": "a" * 64,
                    "size_bytes": 12,
                },
                "signature": "sha256:" + "a" * 64,
            },
            "decision": {
                "status": "update_available",
                "target_version": "2026.09.13+1",
                "reason": "compatible OTA update is available",
            },
        }

    check = check_for_update(
        "https://control.example.test/",
        device_id="pi-lab-01",
        device_token="device-token",
        current_version="2026.09.13+0",
        protocol_version="1",
        fetch_json=fetch_json,
    )

    assert check.update_available is True
    assert check.manifest is not None
    assert check.manifest.version == "2026.09.13+1"
    assert check.token_hosts == {"control.example.test"}
    assert requested_headers == {"X-Robot-Device-Token": "device-token"}


def test_ota_check_cli_applies_available_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = tmp_path / "robot.toml"
    config.write_text(
        """
[runtime]
device_id = "pi-lab-01"
server_url = "https://control.example.test"
device_token = "device-token"
""".strip(),
        encoding="utf-8",
    )
    manifest = UpdateManifest.from_dict(
        {
            "version": "2026.09.13+1",
            "channel": "stable",
            "min_protocol_version": "1",
            "artifact": {
                "url": "https://control.example.test/runtime.tgz",
                "sha256": "a" * 64,
                "size_bytes": 1,
            },
            "signature": "sha256:" + "a" * 64,
        }
    )
    calls: list[tuple[str, object]] = []

    def fake_check(*args: object, **kwargs: object) -> UpdateCheck:
        calls.append(("check", args, kwargs))
        return UpdateCheck(
            update_available=True,
            manifest=manifest,
            token_hosts={"control.example.test"},
            reason="compatible OTA update is available",
        )

    def fake_apply(*args: object, **kwargs: object) -> object:
        calls.append(("apply", args, kwargs))
        return object()

    monkeypatch.setattr("cube_robot_runtime.main.check_for_update", fake_check)
    monkeypatch.setattr("cube_robot_runtime.main.apply_update", fake_apply)

    exit_code = main(
        [
            "ota-check",
            "--config",
            str(config),
            "--state-dir",
            str(tmp_path),
            "--current-version",
            "2026.09.13+0",
            "--apply",
        ]
    )

    assert exit_code == 0
    assert [call[0] for call in calls] == ["check", "apply"]
    output = capsys.readouterr().out
    assert '"status": "applied"' in output
    assert '"target_version": "2026.09.13+1"' in output
