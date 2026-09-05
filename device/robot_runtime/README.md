# robot_runtime (Raspberry Pi)

On-device system for the voice companion: mic capture, turn-taking, barge-in, session mirror, and cloud bridge.

See also:

- [docs/robot-runtime.md](../../docs/robot-runtime.md)
- [docs/companion-remodel.md](../../docs/companion-remodel.md)

## Modules

| Path | Role |
|---|---|
| `audio/` | capture / playback / AEC interfaces |
| `vad/` | turn-taking + barge-in |
| `session/` | interaction loop + Companion State mirror |
| `bridge/` | WebSocket protocol + client stub |
| `router/` | edge/cloud routing stub |
| `runtime.py` | wires the Pi system together |

## Quick start on Pi

```bash
cd device/robot_runtime
python3 -m venv .venv
.source .venv/bin/activate
pip install -e .
export ROBOT_DEVICE_ID=pi-prototype-01
export ROBOT_CLOUD_WS_URL=wss://your-host/api/robot/v1/ws
robot-runtime
```

Systemd unit example: `deploy/robot-runtime.service`.

## Status

Skeleton system with real interfaces. Next: ALSA/PortAudio capture, real WebSocket client, cloud `/api/robot/v1` pairing.
