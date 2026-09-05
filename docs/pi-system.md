# Raspberry Pi System

The companion product needs an on-device OS-level service, not only cloud APIs.

## Process

`robot-runtime` systemd service:

1. Opens mic + speaker
2. Runs VAD / turn-taking / barge-in
3. Maintains local session + Companion State mirror
4. Speaks to cloud over `ROBOT_CLOUD_WS_URL`

## Environment

| Var | Meaning |
|---|---|
| `ROBOT_DEVICE_ID` | Stable device id |
| `ROBOT_DEVICE_TOKEN` | Pairing token from cloud register |
| `ROBOT_CLOUD_WS_URL` | `wss://…/api/robot/v1/ws` |
| `ROBOT_SAMPLE_RATE_HZ` | Default 16000 |
| `ROBOT_ENABLE_BARGE_IN` | Default true |

## Install sketch

```bash
sudo mkdir -p /opt/robot_runtime
sudo rsync -a robot_runtime/ /opt/robot_runtime/
cd /opt/robot_runtime
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
sudo cp deploy/robot-runtime.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now robot-runtime
```

## Hardware notes

- Prefer USB mic or I2S mic HAT with known ALSA device name
- Measure loopback echo; replace `PassthroughEchoCanceller` when AEC lib is chosen
- Keep cloud TTS/audio generation out of Pi; Pi only plays streamed PCM/opus from brain
