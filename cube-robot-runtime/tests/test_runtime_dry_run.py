from cube_robot_runtime.main import RuntimeConfig, main, run_dry_run


def test_dry_run_sends_heartbeat_and_utterance_to_mock_connection() -> None:
    result = run_dry_run(
        RuntimeConfig(
            server_url="mock://robot",
            device_id="pi-lab-01",
            session_id="voice-session-1",
        ),
        utterance="你好",
    )

    assert result.sent_types == ("device.heartbeat", "speech.partial")
    assert result.received_texts == ("我听到了：你好",)


def test_dry_run_accepts_websocket_target_without_opening_a_connection() -> None:
    result = run_dry_run(
        RuntimeConfig(
            server_url="ws://127.0.0.1:8000/api/v1/robot/ws/pi-lab-01",
            device_id="pi-lab-01",
        ),
        utterance="你好",
    )

    assert result.received_texts == ("我听到了：你好",)


def test_dry_run_cli_prints_mock_response(capsys) -> None:
    exit_code = main(
        [
            "dry-run",
            "--server-url",
            "mock://robot",
            "--device-id",
            "pi-lab-01",
            "--utterance",
            "你好",
        ]
    )

    assert exit_code == 0
    assert "我听到了：你好" in capsys.readouterr().out
