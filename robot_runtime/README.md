# robot_runtime

On-device runtime for the Raspberry Pi voice companion.

See [docs/robot-runtime.md](../docs/robot-runtime.md) for architecture and bridge protocol.

## Status

Skeleton only. Next implementation slices:

1. Config + process entry
2. Audio capture / playback stubs
3. Turn-taking + barge-in stubs
4. WebSocket bridge client against cloud protocol
5. Main interaction loop

## Run (placeholder)

```bash
cd robot_runtime
# uv sync  # when pyproject is filled in
# uv run robot-runtime
```
