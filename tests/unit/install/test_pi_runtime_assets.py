from pathlib import Path
import shlex
import tomllib

from cube_robot_runtime.main import main


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


def test_runtime_service_entry_point_accepts_run_config(tmp_path: Path, capsys) -> None:
    root = Path("cube-robot-runtime")
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["scripts"]["cube-robot"] == "cube_robot_runtime.main:main"

    config = tmp_path / "robot.toml"
    config.write_text(
        "[runtime]\ndevice_id = 'pi-lab-01'\nserver_url = 'mock://robot'\n",
        encoding="utf-8",
    )
    assert main(["run", "--config", str(config)]) == 0
    assert "pi-lab-01" in capsys.readouterr().out

    service = (root / "scripts" / "cube-robot.service").read_text(encoding="utf-8")
    exec_start = next(line for line in service.splitlines() if line.startswith("ExecStart="))
    command = shlex.split(exec_start.removeprefix("ExecStart="))
    assert command[-3:] == ["run", "--config", "/etc/cube-robot/robot.toml"]


def test_ota_dry_run_uses_bootstrap_python_without_current_release() -> None:
    script = (Path("cube-robot-runtime") / "scripts" / "ota-update.sh").read_text(encoding="utf-8")
    assert "PYTHON_BIN" in script
    assert 'if "$DRY_RUN"' in script
    assert "python3" in script
    assert "current/bin/python" in script


def test_first_boot_template_path_has_stable_override() -> None:
    script = (Path("cube-robot-runtime") / "scripts" / "first-boot-register.sh").read_text(encoding="utf-8")
    assert "RUNTIME_ROOT" in script
    assert "TEMPLATE_PATH" in script
    assert "robot.toml.example" in script
    assert '"$TEMPLATE_PATH"' in script
