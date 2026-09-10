from pathlib import Path

from cube_robot_runtime.ota.updater import UpdateManifest, select_release, verify_artifact


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
