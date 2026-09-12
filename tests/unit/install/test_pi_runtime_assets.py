import importlib.util
import os
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Self

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
    probe_path = Path("tools") / "robot_voice_probe.py"
    text = probe_path.read_text(encoding="utf-8")

    for required in (
        "/api/v1/auth/login",
        "--no-proxy",
        "default=True",
        "ProxyHandler({})",
    ):
        assert required in text
    spec = importlib.util.spec_from_file_location("robot_voice_probe_test", probe_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.websocket_proxy_options(True) == {
        "http_proxy_host": None,
        "http_proxy_port": None,
        "http_no_proxy": ["*"],
    }
    assert module.websocket_proxy_options(False) == {}


def test_robot_voice_probe_uses_valid_default_ota_version() -> None:
    probe_path = Path("tools") / "robot_voice_probe.py"
    spec = importlib.util.spec_from_file_location("robot_voice_probe_version_test", probe_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    captured: dict[str, str] = {}

    class FakeResponse:
        status = 200

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _limit: int) -> bytes:
            return b'{"decision":{"status":"update_available"}}'

    def fake_open_http(request: object, *, timeout_seconds: float, no_proxy: bool) -> FakeResponse:
        del timeout_seconds, no_proxy
        captured["url"] = request.full_url
        return FakeResponse()

    module.open_http = fake_open_http

    result = module.probe_ota_manifest(
        base_url="http://103.236.93.62:32020",
        device_id="pi-lab-01",
        device_token="placeholder",
        timeout_seconds=1,
        no_proxy=True,
    )

    assert result["ok"] is True
    assert "current_version=2026.09.10%2B0" in captured["url"]
    assert "current_version=probe" not in captured["url"]


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


def test_runtime_voice_once_entry_point_stays_inside_pi_runtime() -> None:
    root = Path("cube-robot-runtime")
    main = (root / "cube_robot_runtime" / "main.py").read_text(encoding="utf-8")
    voice_once = (root / "cube_robot_runtime" / "voice_once.py").read_text(encoding="utf-8")
    config = (root / "config" / "robot.toml.example").read_text(encoding="utf-8")

    assert "voice-once" in main
    assert "audio.start" in voice_once
    assert "tts.audio.done" in voice_once
    assert "[audio]" in config
    assert "voice_id" in config


def test_robot_manual_documents_minimax_and_voice_once_operations() -> None:
    manual = (Path("docs") / "robot-system-manual.md").read_text(encoding="utf-8")
    checklist = (Path("docs") / "robot-field-test.md").read_text(encoding="utf-8")

    for required in (
        "MINIMAX_API_KEY",
        "AGENT_HUB_ROBOT_VOICE_MEDIA_PROVIDER=minimax",
        "voice-once",
        "tts.audio.done",
    ):
        assert required in manual
    assert "played_audio_codecs" in checklist


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
