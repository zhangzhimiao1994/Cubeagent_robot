# Architecture: Agent backend + Pi frontend

## Rule

- **Backend (AI)**: `src/agent_hub/` in this repo — LLM, memory, companion state, STT/TTS if cloud-side, proactive engine.
- **Frontend (device)**: `device/robot_runtime/` on Raspberry Pi — microphone, speaker, turn-taking, barge-in, WebSocket bridge only.
- **The Pi does not run AI models.** No local LLM, no on-device inference, no edge model router.

```text
[Mic] → Pi robot_runtime (VAD / barge-in / session) → WS → agent_hub brain
[Speaker] ← Pi playback ← audio/text from brain ←┘
```

## Monorepo folders

| Path | Role |
|---|---|
| `device/robot_runtime/` | Pi frontend runtime |
| `device/image/` | Flash / first-boot appliance for SD card |
| `src/agent_hub/` | Cloud/backend agent |
| `src/agent_hub/api/routers/robot.py` | Device-facing API |
| `src/agent_hub/companion/` | Companion state / timeline / proactive |
| `src/agent_hub/robot/` | Device registry + bridge hub |

Multimedia generation stays out of companion v1.
