# Cloud Robot API

Brain-side interfaces for Raspberry Pi `robot_runtime`.

Base prefix: `/api/robot/v1`

Router module: `src/agent_hub/api/routers/robot.py`

Wire into FastAPI with:

```python
from agent_hub.api.routers import robot
application.include_router(robot.router)
```

## REST

| Method | Path | Purpose |
|---|---|---|
| POST | `/devices/register` | Create device_id + device_token |
| GET | `/companion-state?device_id=` | Companion State snapshot |
| PATCH | `/companion-state?device_id=` | Patch Companion State |
| GET | `/timeline?device_id=` | Life Timeline list |
| POST | `/timeline?device_id=` | Add life event |
| GET | `/proactive/suggest?device_id=` | Optional nudge text |

## WebSocket

`WS /api/robot/v1/ws` with `X-Device-Token` header or `?device_token=`.

Message types mirror `docs/robot-runtime.md` / `robot_runtime` bridge protocol.

Stub behavior: `utterance.end` returns a short `assistant.text` + `assistant.end`; `barge_in` returns `cancel`.

## Systems

- `agent_hub.companion` — Companion State, Life Timeline, ProactiveEngine
- `agent_hub.robot` — DeviceRegistry, RobotSessionStore, RobotBridgeHub
