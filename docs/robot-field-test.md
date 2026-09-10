# Robot Field Test Checklist

Date: 2026-09-12
Target host: prod-web-02
Public robot gateway: http://103.236.93.62:32020
Device id: pi-lab-01
Token handling: use only the server-configured robot token at test time; do not paste it into this file, logs, commits, screenshots, or chat.

## Before Travel

- [ ] Confirm prod-web-02 is reachable on port 32020 from the test network.
- [ ] Confirm the configured server token maps to `pi-lab-01`.
- [ ] Keep the default no-proxy behavior for the probe unless a controlled network test explicitly requires `--allow-proxy`.
- [ ] Run the hardware-free probe from this repository:

```bash
python tools/robot_voice_probe.py --base-url http://103.236.93.62:32020 --device-id pi-lab-01 --device-token <server-configured token> --utterance "你好"
```

- [ ] Confirm the probe reports an OTA manifest response and a WebSocket `assistant.text.done` response.
- [ ] Confirm the probe reports the `/api/v1/auth/login` path as reachable before relying on the debug surface.
- [ ] If `websocket-client` is missing, install it only in the local test environment or run the probe from the Pi runtime environment where it is already available.

## Pi Runtime Setup

- [ ] Copy the current `cube-robot-runtime` release bundle to the Pi staging area.
- [ ] Run first boot provisioning with `--dry-run` and inspect the planned `/etc/cube-robot` and `/var/lib/cube-robot` paths.
- [ ] Write `/etc/cube-robot/robot.toml` with `device_id = "pi-lab-01"`, the prod-web-02 WebSocket URL, and the device token.
- [ ] Enable `cube-robot.service` only after the dry-run output matches the expected config and state directories.

## OTA Dry-Run

- [ ] Run OTA dry-run before any release switch:

```bash
/usr/local/lib/cube-robot/scripts/ota-update.sh --dry-run --config /etc/cube-robot/robot.toml
```

- [ ] Confirm OTA dry-run reports the staged release directory under `/var/lib/cube-robot/releases`.
- [ ] Confirm OTA dry-run does not modify `/var/lib/cube-robot/current`.
- [ ] Confirm prod-web-02 returns an OTA manifest decision for `pi-lab-01`.

## Audio I/O

- [ ] Verify microphone device selection with a short local audio capture.
- [ ] Record a five-second audio capture in the expected format and confirm the file is non-empty.
- [ ] Verify speaker output with local playback before starting the robot service.
- [ ] Start `cube-robot.service` and confirm one spoken utterance produces playback from the assistant response.
- [ ] Keep one fallback text utterance test available if audio capture fails, so the WebSocket path can still be validated.

## Conversation Path

- [ ] Send "你好" and confirm the robot receives a bounded assistant text response.
- [ ] Repeat with one longer Chinese utterance and confirm no token or secret appears in service logs.
- [ ] Confirm heartbeat/status updates appear server-side for `pi-lab-01`.
- [ ] Confirm playback finished events are recorded after the assistant response is played.

## Rollback

- [ ] Before changing releases, record the current `/var/lib/cube-robot/current` target.
- [ ] If OTA validation fails, stop `cube-robot.service`, restore the previous `current` target, and start the service again.
- [ ] If audio capture or playback fails after a release change, rollback first, then diagnose hardware separately.
- [ ] If prod-web-02 rejects the token, stop the field test and rotate the server-side token before retrying.
- [ ] After rollback, rerun the hardware-free probe and one local playback check before resuming the field test.

## Exit Criteria

- [ ] OTA dry-run succeeds against prod-web-02 on port 32020.
- [ ] Audio capture and playback both work locally on the Pi.
- [ ] The robot WebSocket receives a final utterance and returns assistant text.
- [ ] No real token, secret, or credential is present in repository files, copied logs, screenshots, or reports.
