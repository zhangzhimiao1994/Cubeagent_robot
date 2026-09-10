from agent_hub.robot.ota import OtaArtifact, OtaManifest, OtaStatus, validate_manifest_for_device


def test_ota_manifest_accepts_compatible_stable_update() -> None:
    manifest = OtaManifest(
        version="2026.09.10+001",
        channel="stable",
        min_protocol_version="1",
        artifact=OtaArtifact(
            url="https://updates.example.com/cube-robot-runtime-2026.09.10.tgz",
            sha256="a" * 64,
            size_bytes=12345,
        ),
        signature="sig-test",
        rollback_version="2026.09.01+001",
    )

    decision = validate_manifest_for_device(
        manifest,
        protocol_version="1",
        current_version="2026.09.01+001",
    )

    assert decision.status is OtaStatus.UPDATE_AVAILABLE
    assert decision.target_version == "2026.09.10+001"


def test_ota_manifest_rejects_incompatible_protocol() -> None:
    manifest = OtaManifest(
        version="2026.09.10+001",
        channel="stable",
        min_protocol_version="2",
        artifact=OtaArtifact(
            url="https://updates.example.com/runtime.tgz",
            sha256="b" * 64,
            size_bytes=1,
        ),
        signature="sig-test",
    )

    decision = validate_manifest_for_device(
        manifest,
        protocol_version="1",
        current_version="2026.09.01+001",
    )

    assert decision.status is OtaStatus.INCOMPATIBLE
    assert "protocol" in decision.reason
