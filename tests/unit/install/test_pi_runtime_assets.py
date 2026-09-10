import os
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from cube_robot_runtime.main import load_runtime_config, main


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


def test_robot_voice_probe_asset_documents_required_cli_and_robot_protocol_paths() -> None:
    probe = Path("tools") / "robot_voice_probe.py"
    assert probe.exists(), probe

    text = probe.read_text(encoding="utf-8")
    for required in (
        "--base-url",
        "--device-id",
        "--device-token",
        "--utterance",
        "/api/v1/robot/ws/",
    ):
        assert required in text


def test_robot_voice_probe_checks_login_path_and_bypasses_proxies_by_default() -> None:
    text = (Path("tools") / "robot_voice_probe.py").read_text(encoding="utf-8")

    for required in (
        "/api/v1/auth/login",
        "--no-proxy",
        "default=True",
        "ProxyHandler({})",
        "http_proxy_host=None",
        "http_proxy_port=None",
    ):
        assert required in text


def test_robot_voice_probe_waits_for_final_assistant_websocket_frame() -> None:
    text = (Path("tools") / "robot_voice_probe.py").read_text(encoding="utf-8")

    for required in (
        "--max-ws-frames",
        "for _frame_number in range(max_ws_frames):",
        "assistant.text.done",
        "ignored_types",
    ):
        assert required in text


def test_robot_field_test_checklist_covers_2026_09_12_production_runbook() -> None:
    checklist = Path("docs") / "robot-field-test.md"
    assert checklist.exists(), checklist

    text = checklist.read_text(encoding="utf-8")
    for required in (
        "2026-09-12",
        "prod-web-02",
        "32020",
        "OTA dry-run",
        "audio capture",
        "playback",
        "rollback",
    ):
        assert required in text


def test_runtime_service_entry_point_accepts_run_config(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = Path("cube-robot-runtime")
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["scripts"]["cube-robot"] == "cube_robot_runtime.main:main"

    config = tmp_path / "robot.toml"
    config.write_text(
        "[runtime]\ndevice_id = 'pi-lab-01'\nserver_url = 'mock://robot'\n",
        encoding="utf-8",
    )
    assert main(["run", "--config", str(config), "--once"]) == 0
    assert "pi-lab-01" in capsys.readouterr().out

    service = (root / "scripts" / "cube-robot.service").read_text(encoding="utf-8")
    exec_start = next(line for line in service.splitlines() if line.startswith("ExecStart="))
    command = shlex.split(exec_start.removeprefix("ExecStart="))
    assert command[-3:] == ["run", "--config", "/etc/cube-robot/robot.toml"]


def test_pi_runtime_supports_python_311() -> None:
    root = Path("cube-robot-runtime")
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["requires-python"] == ">=3.11"


def test_runtime_config_rejects_non_table_with_type_error(tmp_path: Path) -> None:
    config = tmp_path / "robot.toml"
    config.write_text('runtime = "not-a-table"\n', encoding="utf-8")

    with pytest.raises(TypeError, match="config must contain a runtime table"):
        load_runtime_config(config)


def test_runtime_service_command_stays_running_without_once(tmp_path: Path) -> None:
    config = tmp_path / "robot.toml"
    config.write_text(
        "[runtime]\ndevice_id = 'pi-lab-01'\nserver_url = 'mock://robot'\n",
        encoding="utf-8",
    )
    environment = os.environ | {"PYTHONPATH": str(Path("cube-robot-runtime").resolve())}
    process = subprocess.Popen(
        [sys.executable, "-m", "cube_robot_runtime.main", "run", "--config", str(config)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=environment,
    )
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            process.wait(timeout=0.5)
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)


def test_ota_dry_run_uses_bootstrap_python_without_current_release() -> None:
    script = (Path("cube-robot-runtime") / "scripts" / "ota-update.sh").read_text(encoding="utf-8")
    bootstrap_branch = script.split('if "$DRY_RUN"; then', 1)[1].split("  else", 1)[0]
    assert "PYTHON_BIN" in bootstrap_branch
    assert "python3" in bootstrap_branch
    assert "current/bin/python" not in bootstrap_branch


def test_updater_timer_uses_dry_run_until_transport_exists() -> None:
    service = (Path("cube-robot-runtime") / "scripts" / "cube-robot-updater.service").read_text(
        encoding="utf-8"
    )

    assert "ota-update.sh --dry-run --config /etc/cube-robot/robot.toml" in service


def test_first_boot_template_path_has_stable_override() -> None:
    script = (Path("cube-robot-runtime") / "scripts" / "first-boot-register.sh").read_text(encoding="utf-8")
    assert "RUNTIME_ROOT" in script
    assert "getent group cube-robot" in script
    assert "groupadd --system cube-robot" in script
    assert "getent passwd cube-robot" in script
    assert "useradd --system --gid cube-robot" in script
    assert 'TEMPLATE_PATH="${TEMPLATE_PATH:-$RUNTIME_ROOT/config/robot.toml.example}"' in script
    assert 'install -m 0640 -o cube-robot -g cube-robot "$TEMPLATE_PATH" "$CONFIG_PATH"' in script
