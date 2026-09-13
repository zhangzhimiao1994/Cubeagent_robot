from pathlib import Path

from cube_robot_runtime.main import main
from cube_robot_runtime.policy import fetch_device_policy


def test_fetch_device_policy_converts_websocket_runtime_url_to_http_policy_url() -> None:
    requested_headers: dict[str, str] = {}

    def fetch_json(url: str, headers: dict[str, str]) -> dict[str, object]:
        requested_headers.update(headers)
        assert url == "http://control.example.test/api/v1/robot/policy/pi-lab-01"
        return {
            "device_id": "pi-lab-01",
            "config": {"volume": 55},
            "policy": {"ota_channel": "stable"},
            "target_version": "2026.09.14+1",
            "policy_version": "v1",
        }

    policy = fetch_device_policy(
        "ws://control.example.test/api/v1/robot/ws/pi-lab-01",
        device_id="pi-lab-01",
        device_token="device-token",
        fetch_json=fetch_json,
    )

    assert policy.target_version == "2026.09.14+1"
    assert policy.config["volume"] == 55
    assert requested_headers == {"X-Robot-Device-Token": "device-token"}


def test_policy_check_cli_prints_server_managed_policy(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    config = tmp_path / "robot.toml"
    config.write_text(
        """
[runtime]
device_id = "pi-lab-01"
server_url = "ws://control.example.test/api/v1/robot/ws/pi-lab-01"
device_token = "device-token"
""".strip(),
        encoding="utf-8",
    )

    def fake_fetch_policy(*args: object, **kwargs: object) -> object:
        from cube_robot_runtime.policy import DevicePolicyBundle

        assert args == ("ws://control.example.test/api/v1/robot/ws/pi-lab-01",)
        assert kwargs["device_id"] == "pi-lab-01"
        assert kwargs["device_token"] == "device-token"
        return DevicePolicyBundle(
            device_id="pi-lab-01",
            config={"volume": 55},
            policy={"ota_channel": "stable"},
            target_version="2026.09.14+1",
            policy_version="v1",
        )

    monkeypatch.setattr("cube_robot_runtime.main.fetch_device_policy", fake_fetch_policy)

    exit_code = main(["policy-check", "--config", str(config)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert '"device_id": "pi-lab-01"' in output
    assert '"target_version": "2026.09.14+1"' in output
    assert '"volume": 55' in output
