# Companion Remodel Plan

Target product: Raspberry Pi voice companion robot with strong long-term memory.
Source product: Cube Agent multi-agent ops console (`agent_hub`).

## Hardware

- Board: Raspberry Pi
- Input: microphone
- Output: speaker (assumed)
- Missing today: full on-device **Robot Runtime** interaction layer

## Two-layer architecture

### Device: `robot_runtime` (on Pi)

Owns the interaction loop:

1. Capture mic audio
2. VAD / turn-taking (user finished speaking?)
3. Barge-in (stop TTS when user speaks)
4. Session + local Companion State mirror
5. Bridge to cloud/local brain over WebSocket
6. Play reply audio
7. Persist memory writes via brain API

### Cloud: `Cubeagent_robot` / `agent_hub`

Owns the brain:

- Conversation reasoning
- Authoritative Companion State
- Long-term memory (`working` / `episodic` / `core`) + Life Timeline
- Proactive triggers (evolve from `scheduler`)
- Optional edge/cloud model routing policy

## Keep / reshape / remove

### Keep and reshape

- `src/agent_hub/memory` → companion memory + Life Timeline
- `src/agent_hub/context` → conversation compaction for long companionship
- `src/agent_hub/scheduler` → Proactive Engine seed
- Model pool / routing → Edge/Cloud Router later
- Channel/auth/db foundations as needed for device auth

### Deprioritize (do not build for v1)

- Dispatch / Discuss multi-agent workbench UX
- Evolution / Darwin skill loops
- OpenClaw computer-control surface
- Skills approval marketplace for companion v1

### Remove

- **Multimedia generation stack** (image / video / audio generation jobs)
  - Product decision: not needed for voice companion v1
  - Scope: `src/agent_hub/multimodal` generation paths, multimedia model presets, related Web console pages, docs that teach multimedia setup
  - Keep only what Robot Runtime needs later for mic/speaker I/O (device-side), not cloud multimedia executors

## Phase 1 (minimum lovable companion)

1. `robot_runtime` listen → turn-take → barge-in → reply loop on Pi
2. Cloud chat + Companion State API for the device bridge
3. Wire existing memory into every companion turn; add Life Timeline write path
4. Strip / gate multimedia generation from product surface

## Phase 2

- Proactive Engine on top of scheduler
- Edge/Cloud Router
- Stronger memory retrieval (beyond keyword)

## Phase 3

- Embodied perception (camera / sensors) if hardware expands
