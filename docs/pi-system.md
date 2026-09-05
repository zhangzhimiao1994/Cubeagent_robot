# Raspberry Pi System

On-device package path: `device/robot_runtime/`.

## Install sketch

```bash
sudo mkdir -p /opt/robot_runtime
sudo rsync -a device/robot_runtime/ /opt/robot_runtime/
cd /opt/robot_runtime
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
sudo cp deploy/robot-runtime.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now robot-runtime
```

Env: `ROBOT_DEVICE_ID`, `ROBOT_DEVICE_TOKEN`, `ROBOT_CLOUD_WS_URL`.
