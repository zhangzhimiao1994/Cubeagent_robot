from __future__ import annotations

from robot_runtime.config import RuntimeConfig
from robot_runtime.session.loop import InteractionLoop


def main() -> None:
    config = RuntimeConfig(device_id="pi-prototype-01")
    loop = InteractionLoop()
    print(
        f"robot_runtime {config.device_id} ready; state={loop.state.value}; "
        f"cloud={config.cloud_ws_url}"
    )
    print("Wire audio/vad/bridge next; this entry is a skeleton.")


if __name__ == "__main__":
    main()
