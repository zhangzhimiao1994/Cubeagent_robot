from pathlib import Path


def test_pi_runtime_assets_are_isolated() -> None:
    root = Path("cube-robot-runtime")
    assert (root / "pyproject.toml").exists()
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        if any(forbidden in text for forbidden in ("agent_hub", "cognition", "hermes")):
            offenders.append(str(path))
    assert offenders == []


def test_pi_provisioning_assets_keep_runtime_state_outside_releases() -> None:
    root = Path("cube-robot-runtime")
    asset_paths = (
        root / "scripts" / "cube-robot.service",
        root / "scripts" / "cube-robot-updater.service",
        root / "scripts" / "cube-robot-updater.timer",
        root / "scripts" / "first-boot-register.sh",
        root / "scripts" / "ota-update.sh",
        root / "config" / "robot.toml.example",
    )

    for path in asset_paths:
        assert path.exists(), path

    scripts = asset_paths[3:5]
    for path in scripts:
        text = path.read_text(encoding="utf-8")
        assert "--dry-run" in text
        assert "/etc/cube-robot" in text
        assert "/var/lib/cube-robot" in text
