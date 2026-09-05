# Device packages

On-device code for the Raspberry Pi companion. Keep this tree separate from the cloud brain under `src/agent_hub/`.

| Path | Role |
|---|---|
| `robot_runtime/` | Mic/speaker, VAD, barge-in, session, cloud bridge |

Cloud APIs live in `src/agent_hub/companion`, `src/agent_hub/robot`, and `src/agent_hub/api/routers/robot.py`.
