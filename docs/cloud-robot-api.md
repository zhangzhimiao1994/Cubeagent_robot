# Cloud Robot API

Brain-side interfaces for Raspberry Pi `device/robot_runtime`.

Code lives under `src/agent_hub/companion`, `src/agent_hub/robot`, and `src/agent_hub/api/routers/robot.py`.

Base prefix: `/api/robot/v1`

Wire with:

```python
from agent_hub.api.routers import robot
application.include_router(robot.router)
```
