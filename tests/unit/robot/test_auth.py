from agent_hub.robot.auth import RobotDeviceTokenStore


def test_robot_device_token_auth_rejects_non_ascii_candidate_without_exception() -> None:
    tokens = RobotDeviceTokenStore.from_secret("pi-lab-01:robot-token")

    assert tokens.authenticate("pi-lab-01", "服务器上的真实token") is False
