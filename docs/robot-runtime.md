# Robot Runtime (Raspberry Pi)

On-device interaction layer for the voice companion. This is not the cloud multi-agent console.

## Goals

- Continuous mic capture with low latency
- Turn-taking: decide when the user finished speaking
- Barge-in: cancel TTS playback when the user speaks
- Local session + Companion State mirror
- Bridge to cloud brain (`agent_hub`) over authenticated WebSocket
- Optional local small-model path (stub in Phase 1)

## Package layout

```text
device/robot_runtime/
  README.md
  pyproject.toml
  src/robot_runtime/
    __init__.py
    main.py
    config.py
    runtime.py
    audio/
    vad/
    session/
    bridge/
    router/
```

Cloud brain stays under `src/agent_hub/` (companion + robot API).

## Bridge protocol

Transport: WebSocket `wss://<host>/api/robot/v1/ws`

See `docs/cloud-robot-api.md` for cloud endpoints.
