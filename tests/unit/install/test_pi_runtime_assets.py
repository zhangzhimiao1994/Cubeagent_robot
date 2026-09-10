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
