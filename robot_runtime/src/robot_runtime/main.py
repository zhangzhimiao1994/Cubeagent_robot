from __future__ import annotations

import asyncio

from robot_runtime.config import RuntimeConfig
from robot_runtime.runtime import RobotRuntime


async def _amain() -> None:
    runtime = RobotRuntime(RuntimeConfig())
    await runtime.start()
    print(
        f"robot_runtime device={runtime.config.device_id} "
        f"state={runtime.loop.state.value} cloud={runtime.config.cloud_ws_url}"
    )
    print("Pi system skeleton online. Wire ALSA capture next.")
    await runtime.stop()


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
