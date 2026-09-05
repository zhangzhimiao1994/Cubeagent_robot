# Companion Remodel Plan

## Architecture (locked)

- **Agent backend** (`src/agent_hub/`): all AI — chat, memory, companion state, STT/TTS orchestration.
- **Pi frontend** (`device/robot_runtime/`): mic/speaker, turn-taking, barge-in, WebSocket client only.
- **Pi does not run AI.**
- **Flashable appliance**: `device/image/` (firstboot on Raspberry Pi OS Lite; optional later .img).

Multimedia generation is out of companion v1.

See `docs/architecture.md`.
